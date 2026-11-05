// V3's normal external-browser design, measured in an isolated installed Edge instance.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'scenetrace-v3-edge-'));
 const proc=spawn('python',['-m','scenetrace','--no-browser'],{cwd:'baseline',env:{...process.env,SCENETRACE_DATA:folder},stdio:'ignore'});
 let browser,address;
 const measurements=[];
 try{
  for(let n=0;n<200;n++){try{address=JSON.parse(await fs.readFile(path.join(folder,'instance.json'),'utf8')).url;if((await fetch(address+'/health')).ok)break;}catch{}await sleep(100);}
  const start=performance.now();
  browser=await chromium.launch({channel:'msedge',headless:false});
  const context=await browser.newContext({viewport:{width:1260,height:840}});
  const page=await context.newPage();
  await page.goto(address);
  await page.locator('#nav button').first().waitFor();
  const ready=(performance.now()-start)/1000;
  const cdp=await browser.newBrowserCDPSession();
  async function measure(stage){
   const info=await cdp.send('SystemInfo.getProcessInfo');
   const ids=info.processInfo.map(p=>p.id);
   const code='import json,sys,psutil; ids=json.loads(sys.argv[1]); print(json.dumps({"rss_mib":round(sum(psutil.Process(i).memory_info().rss for i in ids if psutil.pid_exists(i))/1048576,2)}))';
   const memory=JSON.parse(execFileSync('python',['-c',code,JSON.stringify(ids)],{encoding:'utf8'}));
   measurements.push({stage,...memory,cpu_seconds:info.processInfo.reduce((n,p)=>n+p.cpuTime,0),browser_process_count:ids.length});
  }
  await measure('App only');
  const site=await context.newPage();
  await site.goto('https://www.w3schools.com/html/html5_video.asp',{waitUntil:'domcontentloaded'});
  await site.locator('video').first().waitFor();
  await site.locator('video').first().evaluate(v=>{v.muted=true;return v.play()});
  await site.waitForFunction(()=>document.querySelector('video').currentTime>1);
  await measure('One website tab playing W3Schools video');
  const extras=[];
  for(let i=0;i<4;i++)extras.push(await context.newPage());
  await measure('Five website tabs; four blank');
  for(const p of extras)await p.close();
  await measure('After closing extra tabs');
  const result={scope:'Original v3 backend in a fresh installed Edge instance on Windows CI. Browser memory excludes Python. Third-party page activity and runner load vary. One shared browser context; four extra tabs are blank, not simulated active websites. Live advertising subframes can affect memory.',edge_version:browser.version(),browser_app_ready_seconds:ready,measurements};
  await fs.mkdir('artifacts/performance',{recursive:true});
  await fs.writeFile('artifacts/performance/v3-edge.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{
  if(browser)await browser.close();
  if(address)try{await fetch(address+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json','X-SceneTrace':'local'},body:'{}'})}catch{}
  await Promise.race([new Promise(r=>proc.once('exit',r)),sleep(5000)]);if(proc.exitCode===null)proc.kill();
  await fs.rm(folder,{recursive:true,force:true,maxRetries:10,retryDelay:100});
 }
})().catch(e=>{console.error(e);process.exitCode=1});
