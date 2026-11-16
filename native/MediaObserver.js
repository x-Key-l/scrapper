// Runs in a dedicated DevTools isolated world in every frame. Telemetry only.
(() => {
  if (globalThis.__sceneTraceObserver) return;
  globalThis.__sceneTraceObserver = true;
  let timer, last = '', stopped = false;
  const report = () => {
    timer = null;
    if (stopped) return;
    const nodes = [...document.querySelectorAll('video,audio')].slice(0,64);
    const items = [];
    const add = (value, kind, element) => {
      if (!value) return;
      try {
        const u = new URL(value, location.href);
        if (!/^https?:$/.test(u.protocol) || /\.(ts|m4s|cmfv|cmfa)(?:$|[?#])/i.test(u.href)) return;
        if (items.length >= 128 || items.some(x => x.url === u.href)) return;
        items.push({url:u.href,title:document.title,kind,ad:!!element?.closest('.adsbygoogle,[class*=advert],[id*=advert]')});
      } catch {}
    };
    for (const node of nodes) add(node.currentSrc || node.src || node.querySelector('source')?.src, 'HTML media', node);
    for (const node of [...document.querySelectorAll('a[download]')].slice(0,64))
      if (/\.(mp4|webm|mkv|mov|mp3|m4a|m3u8|mpd)(?:$|[?#])/i.test(node.href)) add(node.href,'Website download',node);
    for (const node of document.querySelectorAll('meta[property="og:video"],meta[property="og:video:url"],meta[property="og:video:secure_url"]')) add(node.content,'Video metadata',node);
    const payload = JSON.stringify({hasVideo:nodes.length>0,playing:nodes.some(n=>!n.paused&&!n.ended&&n.readyState>=2),items});
    if (payload !== last) { last = payload; globalThis.__scenetraceMedia(payload); }
  };
  const schedule = () => { if (!timer && !stopped) timer = setTimeout(report,200); };
  for (const event of ['loadedmetadata','playing','pause','ended','emptied','loadstart']) document.addEventListener(event,schedule,true);
  const observer = new MutationObserver(schedule);
  observer.observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['src','href','content']});
  addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);observer.disconnect();},{once:true});
  addEventListener('pageshow',()=>{if(stopped){stopped=false;observer.observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['src','href','content']});schedule();}});
  schedule();
})();
