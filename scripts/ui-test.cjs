// Actual browser navigation and import/search/save flows. No provider mocks.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'scenetrace-ui-'));
 const python=process.env.SCENETRACE_PYTHON||'python';
 const proc=spawn(python,['-m','scenetrace','--no-browser'],{env:{...process.env,SCENETRACE_DATA:folder},stdio:'ignore'});
 let browser,address;
 try{
  for(let i=0;i<200;i++){try{address=JSON.parse(await fs.readFile(path.join(folder,'instance.json'),'utf8')).url;const r=await fetch(address+'/health');if(r.ok)break}catch{}await delay(100)}
  assert(address,'Application failed to start');
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(address);
  await page.getByRole('button',{name:'Start discovering →'}).click();
  await page.getByRole('heading',{name:'Find something worth watching.',exact:true}).waitFor();
  await page.getByRole('button',{name:'Video Sources',exact:true}).click();
  await page.getByRole('button',{name:'Metadata & imports',exact:true}).click();
  await page.getByRole('heading',{name:'More sources. More possibilities.'}).waitFor();
  await page.getByRole('button',{name:'Import database',exact:true}).click();
  await page.locator('#import-file').setInputFiles({name:'ui-catalog.csv',mimeType:'text/csv',buffer:Buffer.from('id,title,description,year,category\n1,Forest Portal,A girl discovers a mysterious portal in the forest,1994,anime\n2,Motor Road,Fast cars on a highway,2010,movie\n')});
  await page.locator('#map-title').waitFor();
  await page.getByRole('button',{name:'Import and index →'}).click();
  await page.getByText('Import ui-catalog.csv · Finished',{exact:false}).waitFor({timeout:15000});
  await page.getByRole('button',{name:'Deep Search',exact:true}).click();
  await page.getByRole('textbox',{name:'Describe the video you remember'}).fill('girl mysterious forest portal');
  await page.getByText('Optional clues and source selection',{exact:true}).click();
  await page.locator('.source-chip').filter({hasText:'ui-catalog.csv'}).waitFor();
  const chips=page.locator('[data-deep-source]');
  for(let i=0;i<await chips.count();i++){
   const label=await chips.nth(i).locator('..').textContent();
   if(!label.includes('ui-catalog'))await chips.nth(i).uncheck();
  }
  await page.getByRole('button',{name:'Search deeply'}).click();
  try {
   await page.getByRole('heading',{name:'Forest Portal',exact:true}).waitFor({timeout:45000});
  } catch(error) {
   await fs.mkdir('artifacts',{recursive:true});
   await page.screenshot({path:'artifacts/ui-deep-search-failure.png',fullPage:true});
   console.error(await page.locator('body').innerText());
   throw error;
  }
  await page.getByRole('button',{name:'Find viewing options',exact:true}).first().click();
  await page.getByRole('dialog').getByRole('heading',{name:'Forest Portal',exact:true}).waitFor();
  await page.getByRole('button',{name:'Save title',exact:true}).click();
  await page.getByRole('button',{name:'Close dialog'}).click();
  await page.getByRole('button',{name:'Saved Library',exact:true}).click();
  await page.getByRole('heading',{name:'Forest Portal',exact:true}).waitFor();
  await page.getByRole('textbox',{name:'Filter saved library'}).fill('does not exist');
  assert.equal(await page.locator('#saved-results .card').count(),0);
  await page.getByRole('textbox',{name:'Filter saved library'}).fill('');
  // Previewing a nested JSON export must preserve its selected records path and metadata.
  await page.getByRole('button',{name:'Video Sources',exact:true}).click();
  await page.getByRole('button',{name:'Metadata & imports',exact:true}).click();
  await page.getByRole('button',{name:'Import database',exact:true}).click();
  await page.locator('#import-file').setInputFiles({name:'nested.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({payload:{items:[{id:9,title:'Deep Archive',description:'An archival video'}]}}))});
  await page.locator('#import-name').waitFor();
  await page.locator('#import-name').fill('Nested collection');
  await page.locator('#import-role').selectOption('hybrid');
  await page.locator('#import-categories').fill('archive');
  await page.locator('#import-table').fill('payload.items');
  await page.getByRole('button',{name:'Update preview',exact:true}).click();
  await page.locator('#map-title option[value="title"]').waitFor({state:'attached'});
  assert.equal(await page.locator('#import-table').inputValue(),'payload.items');
  assert.equal(await page.locator('#import-name').inputValue(),'Nested collection');
  assert.equal(await page.locator('#import-role').inputValue(),'hybrid');
  assert.equal(await page.locator('#import-categories').inputValue(),'archive');
  await page.getByRole('button',{name:'Import and index →'}).click();
  await page.getByText('Import Nested collection · Finished',{exact:false}).waitFor({timeout:15000});
  const tvmaze=page.locator('#page .source-card').filter({has:page.getByRole('heading',{name:'TVmaze',exact:true})});
  await tvmaze.getByRole('button',{name:'Configure',exact:true}).click();
  page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'Remove source',exact:true}).click();
  await page.getByRole('button',{name:'Find More Sources ↗',exact:true}).click();
  await page.getByRole('textbox',{name:'Describe the database you need'}).fill('television database');
  await page.getByRole('button',{name:'Find sources',exact:true}).click();
  const discovered=page.locator('#discovered .source-card').filter({has:page.getByRole('heading',{name:'TVmaze',exact:true})});
  await discovered.getByRole('button',{name:'Enable connector',exact:true}).click();
  await page.getByRole('button',{name:'Close dialog'}).click();
  await page.getByRole('button',{name:'Video Sources',exact:true}).click();
  await page.getByRole('button',{name:'Metadata & imports',exact:true}).click();
  await page.locator('#page .source-card').filter({has:page.getByRole('heading',{name:'TVmaze',exact:true})}).waitFor();
  for(const label of ['Anime','Quick Search','Video Sources','Link Analyzer','Downloads','Settings','Home']){
   await page.getByRole('button',{name:label,exact:true}).first().click();
   assert(await page.locator('h1').count()>0);
  }
  await page.getByRole('button',{name:'History',exact:true}).click();
  await page.getByRole('button',{name:/Delete search girl mysterious forest portal/}).click();
  await page.getByRole('button',{name:'Undo deletion',exact:true}).waitFor();
  assert.equal(await page.locator('.history-query').filter({hasText:'girl mysterious forest portal'}).count(),0);
  await page.getByRole('button',{name:'Undo deletion',exact:true}).click();
  await page.locator('.history-query').filter({hasText:'girl mysterious forest portal'}).waitFor();
  await page.getByRole('button',{name:'Link Analyzer',exact:true}).click();
  await page.getByText('Analyze and queue several links',{exact:true}).click();
  await page.locator('#many-urls').fill('https://example.com/one.mp4\nhttps://example.com/two.m3u8');
  assert.equal((await page.locator('#many-urls').inputValue()).split('\n').length,2);
  const downloadMarkup=await page.evaluate(()=>watchDownload({analysis_id:'fixture',formats:[{id:'drm',ext:'mp4',height:720,label:'Source · DRM',video:true,audio:true,drm:true}],subtitles:[{language:'en',label:'English'}]}));
  assert(downloadMarkup.includes('Source · DRM'));
  assert(!/name="authorized" required/.test(downloadMarkup));
  assert(downloadMarkup.includes('name="subtitles"'));
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.locator('[name="filename_template"]').fill('%(title)s.%(ext)s');
  await page.getByRole('button',{name:'Save settings',exact:true}).click();
  await page.getByText('Settings saved',{exact:true}).waitFor();
  assert.equal(await page.locator('[name="filename_template"]').inputValue(),'%(title)s.%(ext)s');
  await page.getByRole('button',{name:'Home',exact:true}).click();
  await fs.mkdir('artifacts',{recursive:true});
  await page.screenshot({path:'artifacts/desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'artifacts/mobile.png',fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Mobile layout overflows horizontally');
  assert.deepEqual(errors,[]);
  console.log('PASS: browser onboarding, all navigation, real CSV upload, field mapping, FTS memory search, detail view, saved library, desktop/mobile layout and no JavaScript errors.');
 }finally{
  if(browser)await browser.close();
  if(address){try{await fetch(address+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json','X-SceneTrace':'local'},body:'{}'})}catch{}}
  await Promise.race([new Promise(r=>proc.once('exit',r)),delay(5000)]);
  if(proc.exitCode===null)proc.kill();
  await fs.rm(folder,{recursive:true,force:true,maxRetries:10,retryDelay:100});
 }
})().catch(e=>{console.error(e);process.exitCode=1});
