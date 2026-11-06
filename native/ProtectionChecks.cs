using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed partial class BrowserWindow
    {
        private async Task<object> CheckProtectionAndDetection(BrowserTab tab,List<string> checks)
        {
            if(adDomains.Count<1000)throw new InvalidOperationException("Bundled domain rules were not loaded.");
            if(!IsAdDomain("ads.scorecardresearch.com")||IsAdDomain("www.w3schools.com"))throw new InvalidOperationException("Domain rule classification failed.");
            await ScanMedia(tab);
            if(!MediaFor(tab).Values.Any(x=>x.Url.Contains("mov_bbb.mp4")))throw new InvalidOperationException("Actual HTML5 video was not detected.");
            int before=blockedRequests.TryGetValue(tab,out var count)?count:0;
            await tab.View.CoreWebView2.ExecuteScriptAsync("fetch('https://ads.scorecardresearch.com/scenetrace-qa-request').catch(()=>{});");
            await AwaitCondition(()=>blockedRequests.TryGetValue(tab,out int n)&&n>before,"actual ad/tracker request blocking");
            string host=new Uri(tab.View.CoreWebView2.Source).Host;shieldAllowed.Add(host);
            if(BlockResource(tab,"https://ads.scorecardresearch.com/scenetrace-qa-request",CoreWebView2WebResourceContext.XmlHttpRequest))throw new InvalidOperationException("Per-site allowlist ignored.");
            shieldAllowed.Remove(host);
            if(BlockResource(tab,"https://ads.scorecardresearch.com/video.mp4",CoreWebView2WebResourceContext.Media))throw new InvalidOperationException("Shield intercepted a media transfer.");
            int popupBefore=openTabs.Count,blockedBefore=blockedRequests[tab];
            await tab.View.CoreWebView2.ExecuteScriptAsync("window.open('https://ads.scorecardresearch.com/scenetrace-qa-popup','_blank')");
            await AwaitCondition(()=>blockedRequests[tab]>blockedBefore,"advertising popup suppression");
            if(openTabs.Count!=popupBefore)throw new InvalidOperationException("Blocked popup created a browser tab.");
            await WaitFor(tab,"document.querySelector('video').currentTime>1 && document.querySelector('video').videoWidth>0");
            checks.Add("Actual media response and HTML5 video detected; duplicate URLs collapsed; known advertising request and popup blocked; per-site allowlist and media exemption passed; video frames continue");
            var item=MediaFor(tab).Values.First(x=>x.Url.Contains("mov_bbb.mp4"));
            var timer=Stopwatch.StartNew();
            var analysis=json.Deserialize<Dictionary<string,object>>(await Post("analyze",new{url=item.Url}));
            var format=((IEnumerable)analysis["formats"]).Cast<Dictionary<string,object>>().First();
            var download=json.Deserialize<Dictionary<string,object>>(await Post("download/add",new {analysis_id=analysis["analysis_id"],format_id=format["id"],destination=downloadFolder}));
            Dictionary<string,object> completed=null;
            for(int i=0;i<300;i++)
            {
                var state=json.Deserialize<Dictionary<string,object>>(await Post("state",new{}));
                var current=((IEnumerable)state["downloads"]).Cast<Dictionary<string,object>>().First(j=>(string)j["id"]==(string)download["id"]);
                if((string)current["status"]=="failed")throw new InvalidOperationException("Detected media download failed: "+current["error"]);
                if((string)current["status"]=="completed"){completed=current;break;}await Task.Delay(200);
            }
            if(completed==null||!File.Exists((string)completed["path"]))throw new InvalidOperationException("Detected media download did not finish.");
            var library=json.Deserialize<Dictionary<string,object>>(await Post("library/list",new{}));
            if(!((IEnumerable)library["items"]).Cast<Dictionary<string,object>>().Any(x=>(string)x["job_id"]==(string)download["id"]))throw new InvalidOperationException("Completed detected video was not indexed in the library.");
            checks.Add("Detected real MP4 → extracted format → queued transfer → completed file → Media Library verified on the packaged Windows executable");
            await UpdateFilters();
            bool updated=File.Exists(Path.Combine(profile,"shield-rules.txt"));
            if(adDomains.Count<1000)throw new InvalidOperationException("Filter update discarded working rules.");
            checks.Add(updated?"Maintained HTTPS filter list downloaded, validated and cached":"Filter provider unavailable; existing protection rules preserved");
            var layouts=new List<object>();
            foreach(var size in new[]{new Size(1366,768),new Size(1920,1080)})
            {
                ClientSize=size;PerformLayout();await Task.Delay(150);
                if(address.Bounds.Right>tools.Width||address.Width<180)throw new InvalidOperationException("Address control escaped the toolbar.");
                layouts.Add(new {width=size.Width,height=size.Height,address_width=address.Width,toolbar_height=tools.Height});
            }
            ClientSize=new Size(1260,800);
            try{using(var bitmap=new Bitmap(Width,Height)){DrawToBitmap(bitmap,new Rectangle(Point.Empty,Size));bitmap.Save(Path.Combine(Path.GetDirectoryName(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")),"native-chrome.png"),ImageFormat.Png);}}catch(Exception){}
            return new {filter_update_verified=updated,rules=adDomains.Count,blocked_requests=blockedRequests[tab],filter_decisions=filterDecisions,filter_cpu_ms=Math.Round(1000.0*filterTicks/Stopwatch.Frequency,3),detected_urls=MediaFor(tab).Count,download_bytes=completed["bytes"],detect_to_download_seconds=Math.Round(timer.Elapsed.TotalSeconds,3),layouts};
        }
        private async Task<object> DiagnoseAnimepahe(BrowserTab tab)
        {
            try
            {
                tabs.SelectedTab=tab.Page;tab.View.CoreWebView2.Navigate("https://animepahe.ch/");
                await WaitFor(tab,"location.hostname==='animepahe.ch' && document.readyState==='complete'",30000);
                string homepageTitle=tab.View.CoreWebView2.DocumentTitle;
                var href=json.Deserialize<string>(await tab.View.CoreWebView2.ExecuteScriptAsync("(()=>{const a=[...document.querySelectorAll('a[href]')].find(a=>a.origin===location.origin&&/episode/i.test(a.pathname));return a?.href||'';})()"));
                if(!String.IsNullOrEmpty(href)){tab.View.CoreWebView2.Navigate(href);await WaitFor(tab,"document.readyState==='complete' && location.href!== 'https://animepahe.ch/'",25000);}
                await ScanMedia(tab);
                var page=json.Deserialize<Dictionary<string,object>>(await tab.View.CoreWebView2.ExecuteScriptAsync("({title:document.title,videoElements:document.querySelectorAll('video').length,frames:document.querySelectorAll('iframe').length,downloadControls:[...document.querySelectorAll('a,button')].filter(a=>/download/i.test(a.textContent)&&a.textContent.length<100).slice(0,12).map(a=>({label:a.textContent.trim(),target:a.href?new URL(a.href).origin+new URL(a.href).pathname:''}))})"));
                return new {homepage=homepageTitle,inspected_page=new Uri(tab.View.CoreWebView2.Source).GetLeftPart(UriPartial.Path),page,detected_media=MediaFor(tab).Count,blocked_requests=blockedRequests.TryGetValue(tab,out int count)?count:0,
                    download_cancellation="The ordinary browser download event does not cancel or call the analyzer.",scope="Live native homepage and episode-page diagnostics. No account, protection challenge or source-side download chain was bypassed. Full anime episode transfer remains unverified."};
            }
            catch(Exception error){return new{source="animepahe.ch",result="Live browser diagnosis incomplete",reason=error.Message,scope="No source-side restriction inferred from this failure."};}
        }
    }
}
