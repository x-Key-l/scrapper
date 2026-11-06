using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed partial class BrowserWindow
    {
        private Action<BrowserTab,CoreWebView2DownloadStartingEventArgs> qaDownloadStarting;
        private async Task AwaitCondition(Func<bool> condition,string label,int timeout=30000)
        {
            var deadline=DateTime.UtcNow.AddMilliseconds(timeout);
            while(DateTime.UtcNow<deadline){if(condition())return;await Task.Delay(100);}throw new InvalidOperationException("Timed out: "+label);
        }
        private async Task FlushDownloads(){await AwaitCondition(()=>!syncingDownloads,"download synchronization");await PumpDownloads();}
        private async Task<List<object>> CheckControlledTransfers(BrowserTab tab,List<string> checks)
        {
            var results=new List<object>();
            string origin="https://download.scenetrace.test:"+Environment.GetEnvironmentVariable("SCENETRACE_QA_DOWNLOAD_PORT");
            string folder=Path.Combine(Path.GetDirectoryName(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")),"controlled-transfers");Directory.CreateDirectory(folder);
            tab.View.CoreWebView2.Navigate(origin);
            await WaitFor(tab,"document.title === 'Native download fixture'");
            // Preserve window.opener: the former 'Open(uri)' emulation failed this.
            await tab.View.CoreWebView2.ExecuteScriptAsync("document.getElementById('blank').click()");
            await AwaitCondition(()=>openTabs.Any(t=>t!=tab&&t!=appTab&&t.View?.CoreWebView2?.DocumentTitle=="Popup relationship"),"script-created popup relationship");
            checks.Add("Script-created about:blank popup retains its opener and document relationship");
            tabs.SelectedTab=tab.Page;
            foreach(var popup in openTabs.Where(t=>t!=tab && t!=appTab && t.View?.CoreWebView2?.DocumentTitle=="Popup relationship").ToArray())CloseTab(popup);
            int progressEvents=0;
            NativeTransfer activeTransfer=null;
            Action<BrowserTab,CoreWebView2DownloadStartingEventArgs> destination=(sourceTab,e)=>{
                activeTransfer=nativeTransfers.Values.First(t=>t.Operation==e.DownloadOperation);
                if(e.Cancel)throw new InvalidOperationException("Application canceled controlled native download.");
                e.ResultFilePath=Path.Combine(folder,Guid.NewGuid().ToString("N")+".zip");e.Handled=true;
                e.DownloadOperation.BytesReceivedChanged+=(sender,args)=>progressEvents++;
            };
            qaDownloadStarting=destination;
            try
            {
                foreach(var mode in new[]{"pause","cancel","retry","redirect","popup"})
                {
                    activeTransfer=null;
                    var elapsed=System.Diagnostics.Stopwatch.StartNew();
                    await tab.View.CoreWebView2.ExecuteScriptAsync("document.getElementById('"+(mode=="redirect"?"redirect":mode=="popup"?"popup":"download")+"').click()");
                    await AwaitCondition(()=>activeTransfer!=null,"website ZIP download starting ("+mode+")");
                    var transfer=activeTransfer;var op=transfer.Operation;
                    await AwaitCondition(()=>op.BytesReceived>131072,"native transfer progress");
                    if(mode=="popup")CloseTab(transfer.Tab);
                    await FlushDownloads();
                    if(mode=="pause"||mode=="cancel")
                    {
                        await Post("download/control",new {id=transfer.Id,action=mode});await FlushDownloads();
                        await AwaitCondition(()=>op.State==CoreWebView2DownloadState.Interrupted,"native "+mode);
                        if(mode=="pause")
                        {
                            if(!op.CanResume)throw new InvalidOperationException("Range-capable native transfer cannot resume.");
                            await FlushDownloads();await Post("download/control",new {id=transfer.Id,action="resume"});await FlushDownloads();
                        }
                        else
                        {
                            if(op.InterruptReason!=CoreWebView2DownloadInterruptReason.UserCanceled)throw new InvalidOperationException("Wrong cancellation reason.");
                            results.Add(new{mode,state="Cancelled",bytes=op.BytesReceived});continue;
                        }
                    }
                    await AwaitCondition(()=>op.State==CoreWebView2DownloadState.Completed,"ZIP transfer completion");
                    using(var file=File.OpenRead(op.ResultFilePath))using(var hash=SHA256.Create())
                        results.Add(new{mode,state="Completed",bytes=file.Length,seconds=Math.Round(elapsed.Elapsed.TotalSeconds,3),sha256=BitConverter.ToString(hash.ComputeHash(file)).Replace("-","").ToLowerInvariant()});
                }
                if(progressEvents==0)throw new InvalidOperationException("Slow native download emitted no progress events.");
                await FlushDownloads();
                var state=json.Deserialize<Dictionary<string,object>>(await Post("state",new{}));
                var jobs=((System.Collections.IEnumerable)state["downloads"]).Cast<Dictionary<string,object>>().ToArray();
                if(jobs.Count(j=>(string)j["engine"]=="browser"&&(string)j["status"]=="completed")<3)throw new InvalidOperationException("Native downloads missing from unified Download Center.");
                checks.Add("Real HTTP ZIP buttons, redirect, chosen paths, progressive bytes, pause/range-resume, cancel and fresh retry verified through unified Download Center");
                return results;
            }
            finally{qaDownloadStarting=null;}
        }
    }
}
