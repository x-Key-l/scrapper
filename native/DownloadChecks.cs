using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed partial class BrowserWindow
    {
        // The handler runs AFTER the production handler. Never clear Cancel here:
        // doing so would conceal the exact regression this test must catch.
        private async Task<object> CheckWebsiteDownload(BrowserTab tab, string page, string file, string extension)
        {
            tabs.SelectedTab=tab.Page;
            await ActivateTab();
            tab.View.CoreWebView2.Navigate(page);
            await WaitFor(tab, "location.href.startsWith(" + json.Serialize(page) + ") && document.readyState === 'complete'", 35000);
            var folder = Path.Combine(Path.GetDirectoryName(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")), "transfers");
            Directory.CreateDirectory(folder);
            var destination = Path.Combine(folder, Guid.NewGuid().ToString("N") + extension);
            var complete = new TaskCompletionSource<CoreWebView2DownloadOperation>();
            int progressEvents = 0;
            var elapsed = Stopwatch.StartNew();
            EventHandler<CoreWebView2DownloadStartingEventArgs> handler = (sender, args) => {
                if (args.Cancel) { complete.TrySetException(new InvalidOperationException("SceneTrace canceled an ordinary website download.")); return; }
                args.ResultFilePath = destination;
                args.Handled = true; // Suppress only the interactive QA dialog, never the transfer.
                var operation = args.DownloadOperation;
                operation.BytesReceivedChanged += (s, e) => progressEvents++;
                operation.StateChanged += (s, e) => {
                    if (operation.State == CoreWebView2DownloadState.Completed) complete.TrySetResult(operation);
                    if (operation.State == CoreWebView2DownloadState.Interrupted)
                        complete.TrySetException(new InvalidOperationException("Native transfer interrupted: " + operation.InterruptReason));
                };
            };
            tab.View.CoreWebView2.DownloadStarting += handler;
            try
            {
                // An ordinary website download control, not a media-analyzer call.
                await tab.View.CoreWebView2.ExecuteScriptAsync("(()=>{let a=document.createElement('a');a.href=" + json.Serialize(file) + ";a.download='SceneTrace-test" + extension + "';a.textContent='Download test file';document.body.append(a);a.click();})()");
                if (await Task.WhenAny(complete.Task, Task.Delay(60000)) != complete.Task)
                    throw new InvalidOperationException("The website download did not complete within 60 seconds.");
                var result = await complete.Task;
                var bytes = File.ReadAllBytes(destination);
                if (bytes.Length < 100 || result.BytesReceived != bytes.Length) throw new InvalidOperationException("Native download byte count did not match the file on disk.");
                if (extension == ".mp4" && System.Text.Encoding.ASCII.GetString(bytes, 4, 4) != "ftyp") throw new InvalidOperationException("MP4 download contained no MP4 file header.");
                if (extension == ".pdf" && System.Text.Encoding.ASCII.GetString(bytes, 0, 4) != "%PDF") throw new InvalidOperationException("PDF download contained no PDF file header.");
                using (var hash = SHA256.Create())
                    return new { source = file, bytes = bytes.Length, progress_events = progressEvents, seconds = Math.Round(elapsed.Elapsed.TotalSeconds, 3),
                        sha256 = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(), destination, state = result.State.ToString() };
            }
            finally { tab.View.CoreWebView2.DownloadStarting -= handler; }
        }
    }
}
