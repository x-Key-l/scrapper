// Exercise the same isolated-world CDP setup as the native host.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'), os=require('node:os'), path=require('node:path');
const {execFileSync}=require('node:child_process');
const http=require('node:http'), assert=require('node:assert/strict');
(async()=>{
 const temp=await fs.mkdtemp(path.join(os.tmpdir(),'scenetrace-detector-'));
 const ffmpeg=execFileSync(process.env.SCENETRACE_PYTHON||'python',['-c','from scenetrace.media import ffmpeg_path; print(ffmpeg_path())'],{encoding:'utf8'}).trim();
 execFileSync(ffmpeg,['-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=10','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',path.join(temp,'sample.mp4')]);
 const media=await fs.readFile(path.join(temp,'sample.mp4'));
 const server=http.createServer((req,res)=>{
  if(req.url.startsWith('/sample.mp4')){res.writeHead(200,{'Content-Type':'video/mp4','Content-Length':media.length});res.end(media);}
  else {res.writeHead(200,{'Content-Type':'text/html'});res.end('<!doctype html><title>Authorized generated fixture</title><body></body>');}
 });
 await new Promise(r=>server.listen(0,'0.0.0.0',r));
 const port=server.address().port, reports=[];
 let browser;
 try {
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage();
  const cdp=await page.context().newCDPSession(page);
  cdp.on('Runtime.bindingCalled',e=>reports.push(JSON.parse(e.payload)));
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Runtime.addBinding',{name:'__scenetraceMedia',executionContextName:'SceneTraceMedia'});
  await cdp.send('Page.addScriptToEvaluateOnNewDocument',{source:await fs.readFile('native/MediaObserver.js','utf8'),worldName:'SceneTraceMedia'});
  await page.goto(`http://127.0.0.1:${port}/`);
  assert.equal(await page.evaluate(()=>typeof globalThis.__scenetraceMedia),'undefined','Telemetry binding must stay outside the page world');
  await page.evaluate(port=>{const f=document.createElement('iframe');f.src=`http://localhost:${port}/frame`;document.body.append(f);},port);
  await page.waitForFunction(()=>document.querySelector('iframe')?.contentWindow);
  const frame=await (await page.$('iframe')).contentFrame();
  await frame.waitForLoadState();
  await frame.evaluate(async()=>{const v=document.createElement('video');v.muted=true;v.src='/sample.mp4';document.body.append(v);await v.play();});
  await frame.waitForFunction(()=>document.querySelector('video').currentTime>0.2);
  for(let i=0;i<40&&!reports.some(x=>x.playing&&x.items.some(i=>i.url.includes('localhost')));i++)await page.waitForTimeout(100);
  assert(reports.some(x=>x.playing&&x.items.some(i=>i.url.includes('localhost'))),'Cross-origin delayed playing media was not reported');
  await page.evaluate(()=>{const v=document.createElement('video');v.src=URL.createObjectURL(new MediaSource());document.body.append(v);const a=document.createElement('a');a.download='segment';a.href='/piece.m4s';document.body.append(a);});
  await page.waitForTimeout(500);
  assert(reports.some(x=>x.hasVideo&&x.items.length===0),'Blob player presence must be distinct from a downloadable resource');
  assert(!reports.some(x=>x.items.some(i=>i.url.startsWith('blob:')||i.url.includes('piece.m4s'))));
  const before=reports.length;await page.waitForTimeout(600);assert.equal(reports.length,before,'Idle observer must not continuously emit scans');
  console.log('PASS: cross-origin delayed HTML5 playback, blob player-only state, segment exclusion, and idle observation deduplication.');
 } finally {if(browser)await browser.close();await new Promise(r=>server.close(r));await fs.rm(temp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
