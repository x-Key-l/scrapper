using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed partial class BrowserWindow
    {
        private async Task WaitFor(BrowserTab tab, string expression, int milliseconds = 20000)
        {
            var timer = Stopwatch.StartNew();
            while (timer.ElapsedMilliseconds < milliseconds)
            {
                if (tab.View?.CoreWebView2 != null && await tab.View.CoreWebView2.ExecuteScriptAsync(expression) == "true") return;
                await Task.Delay(100);
            }
            throw new InvalidOperationException("Browser check timed out: " + expression);
        }

        private object BrowserMemory(string stage)
        {
            var processes = environment.GetProcessInfos();
            long rss = Process.GetCurrentProcess().WorkingSet64;
            double cpu = Process.GetCurrentProcess().TotalProcessorTime.TotalSeconds;
            foreach (var info in processes)
            {
                try
                {
                    using (var process = Process.GetProcessById(info.ProcessId))
                    {
                        rss += process.WorkingSet64;
                        cpu += process.TotalProcessorTime.TotalSeconds;
                    }
                }
                catch (ArgumentException) { }
            }
            return new { stage, browser_and_host_rss_mib = Math.Round(rss / 1048576.0, 2), cpu_seconds = cpu,
                         browser_process_count = processes.Count, allocated_tabs = openTabs.Count(t => t.View != null),
                         total_tabs = openTabs.Count };
        }

        private async Task RunChecks()
        {
            var reportPath = Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT");
            var checks = new List<string>();
            var measurements = new List<object>();
            try
            {
                await WaitFor(appTab, "Boolean(document.querySelector('#nav button'))");
                double appReady = started.Elapsed.TotalSeconds;
                measurements.Add(BrowserMemory("App only"));
                string fixture = Environment.GetEnvironmentVariable("SCENETRACE_TEST_FIXTURES");
                if (String.IsNullOrEmpty(fixture)) throw new InvalidOperationException("The browser QA fixture folder is required.");
                var tab = CreateTab("https://fixture.scenetrace.test/one.html");
                tabs.SelectedTab = tab.Page;
                await EnsureTab(tab);
                tab.View.CoreWebView2.SetVirtualHostNameToFolderMapping("fixture.scenetrace.test", fixture, CoreWebView2HostResourceAccessKind.DenyCors);
                tab.View.CoreWebView2.Navigate("https://fixture.scenetrace.test/one.html");
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture one'");
                if (tab.View.CoreWebView2.Settings.IsWebMessageEnabled || tab.View.CoreWebView2.Settings.AreHostObjectsAllowed)
                    throw new InvalidOperationException("External website bridge was enabled.");
                string bridge = await tab.View.CoreWebView2.ExecuteScriptAsync("(()=>{try{window.chrome.webview.postMessage({action:'open',url:'file:///C:/'});return false}catch(e){return true}})()");
                if (bridge != "true") throw new InvalidOperationException("Website posted a native message.");
                // ExecuteScriptAsync does not unwrap promises. Record the asynchronous result in a test-page variable.
                await tab.View.CoreWebView2.ExecuteScriptAsync(
                    "window.isolationResult='pending';fetch(" + json.Serialize(appOrigin + "/api/state") +
                    ",{method:'POST',headers:{'Content-Type':'application/json','X-SceneTrace':'local'},body:'{}'}).then(r=>window.isolationResult=r.ok?'leaked':'blocked').catch(()=>window.isolationResult='blocked')");
                await WaitFor(tab, "window.isolationResult === 'blocked'");
                checks.Add("External website native bridge and local API requests blocked");
                tab.View.CoreWebView2.Navigate("https://fixture.scenetrace.test/two.html");
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture two'");
                tab.View.GoBack();
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture one'");
                tab.View.GoForward();
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture two'");
                tab.View.Reload();
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture two'");
                find.Text = "Second page";
                await FindText();
                await WaitFor(tab, "window.getSelection().toString().includes('Second page')");
                checks.Add("Address navigation, back, forward, refresh and find text");
                measurements.Add(BrowserMemory("One website tab"));
                var lazy = CreateTab("https://fixture.scenetrace.test/one.html");
                if (lazy.View != null) throw new InvalidOperationException("Background tab was allocated eagerly.");
                tabs.SelectedTab = lazy.Page;
                await EnsureTab(lazy);
                lazy.View.CoreWebView2.SetVirtualHostNameToFolderMapping("fixture.scenetrace.test", fixture, CoreWebView2HostResourceAccessKind.DenyCors);
                lazy.View.CoreWebView2.Navigate(lazy.Pending);
                await WaitFor(lazy, "document.title === 'SceneTrace browser fixture one'");
                tabs.SelectedTab = tab.Page;
                await WaitFor(tab, "document.title === 'SceneTrace browser fixture two'");
                checks.Add("Lazy tabs preserve independent navigation");
                for (int i = 0; i < 3; i++) CreateTab("https://fixture.scenetrace.test/one.html");
                measurements.Add(BrowserMemory("Five website tabs with four inactive"));
                foreach (var extra in openTabs.Where(t => !t.Trusted && t != tab).ToArray()) CloseTab(extra);
                checks.Add("Closed tab views disposed");
                string before = tab.View.CoreWebView2.Source;
                tab.View.CoreWebView2.Navigate("file:///C:/Windows/win.ini");
                await Task.Delay(300);
                if (tab.View.CoreWebView2.Source != before) throw new InvalidOperationException("File navigation escaped isolation.");
                checks.Add("Local file navigation blocked");
                tab.View.CoreWebView2.Navigate("https://www.w3schools.com/html/html5_video.asp");
                await WaitFor(tab, "document.querySelector('video') !== null", 35000);
                await tab.View.CoreWebView2.ExecuteScriptAsync("document.querySelector('video').muted=true;document.querySelector('video').play()");
                await WaitFor(tab, "document.querySelector('video').currentTime>1 && document.querySelector('video').videoWidth>0");
                checks.Add("W3Schools website navigated and actual native WebView2 video frames advanced");
                var shot = json.Deserialize<Dictionary<string, object>>(await tab.View.CoreWebView2.CallDevToolsProtocolMethodAsync("Page.captureScreenshot", "{}"));
                Directory.CreateDirectory(Path.GetDirectoryName(reportPath));
                File.WriteAllBytes(Path.Combine(Path.GetDirectoryName(reportPath), "native-browser-playing.png"), Convert.FromBase64String((string)shot["data"]));
                await Post("browser/bookmark", new { url = tab.View.CoreWebView2.Source, title = tab.View.CoreWebView2.DocumentTitle });
                checks.Add("Browser bookmark saved through authenticated app integration");
                SendToApp("deep-site");
                await WaitFor(appTab, "document.body.innerText.includes('Deep Search')");
                checks.Add("Browser action returns to SceneTrace search");
                measurements.Add(BrowserMemory("After website playback"));
                File.WriteAllText(reportPath, json.Serialize(new { success = true, runtime = environment.BrowserVersionString,
                    app_ready_seconds = Math.Round(appReady, 3), checks, measurements,
                    scope = "Actual packaged WinForms WebView2 host on Windows CI. Memory includes the host and shared WebView2 processes, backend measured separately." }));
                Environment.ExitCode = 0;
                Close();
            }
            catch (Exception error)
            {
                File.WriteAllText(reportPath, json.Serialize(new { success = false, checks, measurements, error = error.ToString() }));
                Environment.ExitCode = 1;
                Close();
            }
        }
    }
}
