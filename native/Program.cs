using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace SceneTrace
{
    internal sealed class BrowserTab
    {
        internal Panel Page;
        internal WebView2 View;
        internal string Pending;
        internal bool Trusted;
        internal bool Loading;
        internal bool Creating;
        internal bool Closed;
        internal bool DownloadOnly;
        internal long Started;
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                CoreWebView2Environment.GetAvailableBrowserVersionString();
                Application.Run(new BrowserWindow());
            }
            catch (WebView2RuntimeNotFoundException)
            {
                if (String.IsNullOrEmpty(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")))
                    MessageBox.Show("The integrated browser needs Microsoft Edge WebView2 Runtime. SceneTrace will open in your default browser. Install WebView2 Evergreen from Microsoft to enable integrated tabs.", "SceneTrace", MessageBoxButtons.OK, MessageBoxIcon.Information);
                Environment.ExitCode = 3;
            }
            catch (Exception error)
            {
                var path = Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT");
                if (!String.IsNullOrEmpty(path)) File.WriteAllText(path, error.ToString());
                else MessageBox.Show("The integrated browser could not start. SceneTrace will open in your default browser.", "SceneTrace");
                Environment.ExitCode = 2;
            }
        }
    }

    internal sealed partial class BrowserWindow : Form
    {
        private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = 4194304 };
        private readonly HttpClient client = new HttpClient(new HttpClientHandler { UseProxy = false });
        private readonly string appOrigin = Environment.GetEnvironmentVariable("SCENETRACE_APP_URL");
        private readonly string profile = Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_PROFILE");
        private readonly BrowserTabs tabs = new BrowserTabs { Dock = DockStyle.Fill };
        private readonly ToolStrip tools = new ToolStrip { GripStyle = ToolStripGripStyle.Hidden, Dock = DockStyle.Top };
        private readonly RoundedAddress address = new RoundedAddress { AutoSize = false, Width = 390 };
        private readonly ToolStripTextBox find = new ToolStripTextBox { AutoSize = false, Width = 130 };
        private readonly ToolStripStatusLabel status = new ToolStripStatusLabel { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
        private readonly ToolStripProgressBar progress = new ToolStripProgressBar { Style = ProgressBarStyle.Marquee, Visible = false };
        private readonly List<BrowserTab> openTabs = new List<BrowserTab>();
        private readonly System.Windows.Forms.Timer activity = new System.Windows.Forms.Timer { Interval = 1000 };
        private CoreWebView2Environment environment;
        private EventWaitHandle focusEvent;
        private bool closing;
        private BrowserTab appTab;
        private readonly Stopwatch started = Stopwatch.StartNew();
        private readonly TaskCompletionSource<bool> browserExited = new TaskCompletionSource<bool>();

        internal BrowserWindow()
        {
            if (!Uri.TryCreate(appOrigin, UriKind.Absolute, out var origin) || origin.Scheme != "http" || origin.Host != "127.0.0.1")
                throw new InvalidOperationException("The SceneTrace local address is missing.");
            Text = "SceneTrace";
            Font = new Font("Segoe UI", 10F);
            AutoScaleMode = AutoScaleMode.Dpi;
            Size = new Size(1260, 840);
            MinimumSize = new Size(800, 600);
            BackColor = Color.FromArgb(19, 25, 34);
            ForeColor = Color.White;
            tools.BackColor = BackColor;
            tools.ForeColor = ForeColor;
            tools.Renderer = new ChromeRenderer();
            tools.Padding = new Padding(6,5,6,5);
            tools.AutoSize = false;
            tools.Height = 48;
            AddButton("Home", () => SelectApp("home"));
            AddButton("←", () => { if (Current?.View?.CoreWebView2?.CanGoBack == true) Current.View.GoBack(); }, "Back");
            AddButton("→", () => { if (Current?.View?.CoreWebView2?.CanGoForward == true) Current.View.GoForward(); }, "Forward");
            AddButton("↻", Reload, "Refresh page");
            tools.Items.Add(address);
            address.AccessibleName = "Website address";
            address.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) { NavigateAddress(); e.SuppressKeyPress = true; } };

            tabs.NewRequested += () => Open("https://www.wikipedia.org/", true);
            tabs.CloseRequested += page => CloseTab(page.Tag as BrowserTab);
            AddButton("☆", Bookmark, "Bookmark page");
            var actions = new ToolStripDropDownButton("☰") { ToolTipText = "Search, video and browser menu", AccessibleName = "Browser menu" };
            AddMenu(actions, "Quick search this website", () => SendToApp("quick-site"));
            AddMenu(actions, "Deep search this website", () => SendToApp("deep-site"));
            AddMenu(actions, "Deep search all sources", () => SendToApp("deep-all"));
            AddMenu(actions, "Add website as source", () => SendToApp("add-source"));
            AddMenu(actions, "Inspect current video", () => SendToApp("inspect"));
            AddMenu(actions, "Save current page", () => SendToApp("save-page"));
            AddMenu(actions, "Open in external browser", OpenExternal);
            SetupShield();
            SetupDetector();
            tools.Items.Add(actions);
            AddButton("↓", () => SelectApp("downloads"), "Download Center");
            AddMenu(actions, "Browser downloads / Save As", () => Current?.View?.CoreWebView2?.OpenDefaultDownloadDialog());
            find.Visible = false;
            find.BackColor = Color.FromArgb(36,40,49);find.ForeColor = Color.White;find.BorderStyle=BorderStyle.FixedSingle;
            AddMenu(actions, "Find text on page", () => {find.Visible=true;find.Focus();});
            tools.Items.Add(find);
            find.AccessibleName = "Find text on page";
            find.KeyDown += async (s, e) => { if (e.KeyCode == Keys.Enter) { await FindText(); e.SuppressKeyPress = true; } };

            var bar = new StatusStrip();
            bar.Items.Add(status);
            bar.Items.Add(progress);
            Controls.Add(tabs);
            tabs.SetToolbar(tools);
            tools.Layout += (s,e) => FitAddress();
            Resize += (s,e) => FitAddress();
            Controls.Add(bar);
            tabs.SelectedIndexChanged += async (s, e) => {
                try { await ActivateTab(); }
                catch (Exception) { status.Text = "This tab could not start. Refresh or open it externally."; }
            };
            client.DefaultRequestHeaders.Add("X-SceneTrace", "local");
            client.DefaultRequestHeaders.Add("X-SceneTrace-Desktop", Environment.GetEnvironmentVariable("SCENETRACE_DESKTOP_TOKEN"));
            client.Timeout = TimeSpan.FromSeconds(65);
            var eventName = Environment.GetEnvironmentVariable("SCENETRACE_FOCUS_EVENT");
            if (!String.IsNullOrEmpty(eventName)) focusEvent = new EventWaitHandle(false, EventResetMode.AutoReset, eventName);
            activity.Tick += async (s, e) => {
                if (focusEvent?.WaitOne(0) == true) { WindowState = FormWindowState.Normal; Show(); Activate(); }
                await PumpDownloads();
            };
            Shown += async (s, e) => await StartBrowser();
            FormClosing += async (s, e) => {
                if (closing) return;
                e.Cancel = true;
                closing = true;
                activity.Stop();
                foreach (var tab in openTabs.ToArray()) DisposeTab(tab);
                if (environment != null) await Task.WhenAny(browserExited.Task, Task.Delay(3000));
                Close();
            };
            FormClosed += (s, e) => {
                foreach (var tab in openTabs.ToArray()) DisposeTab(tab);
                focusEvent?.Dispose();
                client.Dispose();
            };
        }

        [System.Runtime.InteropServices.DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr window,int attribute,ref int value,int size);
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try{int dark=1;if(DwmSetWindowAttribute(Handle,20,ref dark,4)!=0)DwmSetWindowAttribute(Handle,19,ref dark,4);}catch(Exception){}
        }

        private bool fittingAddress;
        private void FitAddress()
        {
            if(fittingAddress || tools.Width<300)return;
            fittingAddress=true;
            try{int occupied=tools.Padding.Horizontal+28;foreach(ToolStripItem item in tools.Items)if(item!=address && item.Available)occupied+=item.Width+item.Margin.Horizontal;address.Width=Math.Max(160,tools.Width-occupied);}finally{fittingAddress=false;}
        }

        private BrowserTab Current => tabs.SelectedTab?.Tag as BrowserTab;

        private void AddButton(string text, Action action, string label = null)
        {
            var button = new ToolStripButton(text) { ToolTipText = label ?? text, AccessibleName = label ?? text };
            button.Click += (s, e) => action();
            tools.Items.Add(button);
        }

        private void AddMenu(ToolStripDropDownButton menu, string label, Action action)
        {
            menu.DropDownItems.Add(label, null, (s, e) => action());
        }

        private async Task StartBrowser()
        {
            try
            {
                Directory.CreateDirectory(profile);
                var browserOptions = new CoreWebView2EnvironmentOptions();
                if (!String.IsNullOrEmpty(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")) && !String.IsNullOrEmpty(Environment.GetEnvironmentVariable("SCENETRACE_QA_DOWNLOAD_PORT")))
                    browserOptions.AdditionalBrowserArguments = "--host-resolver-rules=\"MAP download.scenetrace.test 127.0.0.1\"";
                environment = await CoreWebView2Environment.CreateAsync(null, profile, browserOptions);
                environment.BrowserProcessExited += (sender, eventArgs) => browserExited.TrySetResult(true);
                appTab = CreateTab(appOrigin, true);
                tabs.SelectedTab = appTab.Page;
                await EnsureTab(appTab);
                await Post("desktop/event", new { action = "ready", runtime = environment.BrowserVersionString });
                await PumpDownloads();
                activity.Start();
                if (!String.IsNullOrEmpty(Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT")))
                    await RunChecks();
            }
            catch (Exception error)
            {
                status.Text = "Browser could not start. Open SceneTrace in your default browser.";
                var report = Environment.GetEnvironmentVariable("SCENETRACE_BROWSER_REPORT");
                if (!String.IsNullOrEmpty(report)) File.WriteAllText(report, json.Serialize(new { success = false, error = error.ToString() }));
                Environment.ExitCode = 2;
                Close();
            }
        }

        private BrowserTab CreateTab(string value, bool trusted = false)
        {
            var tab = new BrowserTab { Pending = value, Trusted = trusted, Page = new Panel { Text = trusted ? "SceneTrace" : "New tab" } };
            tab.Page.Tag = tab;
            tab.Page.BackColor = BackColor;
            openTabs.Add(tab);
            tabs.TabPages.Add(tab.Page);
            return tab;
        }

        private void Open(string value, bool foreground)
        {
            if (!AllowedWebsite(value)) { status.Text = "Use a public HTTP or HTTPS website address."; return; }
            var tab = CreateTab(value);
            if (foreground) tabs.SelectedTab = tab.Page;
        }

        private async Task ActivateTab()
        {
            if (environment == null || closing) return;
            var selected = Current;
            if (selected == null) return;
            foreach (var other in openTabs.Where(t => t != selected && t.View?.CoreWebView2 != null))
            {
                other.View.Visible = false;
                if (!other.Trusted)
                {
                    try { await other.View.CoreWebView2.TrySuspendAsync(); } catch (Exception) { }
                }
            }
            await EnsureTab(selected);
            if (selected.Closed || selected.View == null) return;
            selected.View.Visible = true;
            try { selected.View.CoreWebView2.Resume(); } catch (Exception) { }
            UpdateChrome(selected);
        }

        private async Task EnsureTab(BrowserTab tab, bool navigate = true)
        {
            while (tab.Creating && !tab.Closed) await Task.Delay(20);
            if (tab.Closed || tab.View != null) return;
            tab.Creating = true;
            var view = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
            tab.View = view;
            tab.Page.Controls.Add(view);
            try
            {
                var options = environment.CreateCoreWebView2ControllerOptions();
                options.ProfileName = tab.Trusted ? "SceneTraceApp" : "Websites";
                await view.EnsureCoreWebView2Async(environment, options);
                if (tab.Closed) return;
                var core = view.CoreWebView2;
                core.Settings.AreHostObjectsAllowed = false;
                core.Settings.IsWebMessageEnabled = tab.Trusted;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.IsStatusBarEnabled = false;
                core.Settings.IsPasswordAutosaveEnabled = false;
                core.Settings.IsGeneralAutofillEnabled = false;
                core.NewWindowRequested += async (s, e) => {
                    if (tab.Trusted) {e.Handled=true;if(AllowedWebsite(e.Uri))Open(e.Uri,true);return;}
                    if (BlockPopup(tab,e)) {e.Handled=true;return;}
                    if (e.Uri != "about:blank" && !AllowedWebsite(e.Uri)) {e.Handled=true;return;}
                    var deferred=e.GetDeferral();
                    try {
                        var popup=CreateTab(e.Uri);
                        await EnsureTab(popup,false);
                        e.NewWindow=popup.View.CoreWebView2;
                        e.Handled=true;
                        tabs.SelectedTab=popup.Page;
                    } catch(Exception) {status.Text="The popup could not open. Retry its button or open this page externally.";}
                    finally {deferred.Complete();}
                };
                core.PermissionRequested += (s, e) => {
                    // Preserve WebView2's download permission flow. Denying every
                    // permission silently blocked a site's second automatic file.
                    if(e.PermissionKind==CoreWebView2PermissionKind.MultipleAutomaticDownloads || e.PermissionKind==CoreWebView2PermissionKind.FileReadWrite)
                        e.State=CoreWebView2PermissionState.Default;
                    else e.State = CoreWebView2PermissionState.Deny;
                };
                core.DownloadStarting += (s, e) => TrackDownload(tab, e);
                core.WebResourceResponseReceived += (s, e) => ObserveMedia(tab, e);
                core.NavigationStarting += (s, e) => {
                    if (!tab.Trusted && !e.IsRedirected) { detected.Remove(tab); videoElements.Remove(tab); blockedRequests[tab] = 0; UpdateDetector(); }
                    bool allowed = tab.Trusted ? IsApp(e.Uri) : e.Uri == "about:blank" || AllowedWebsite(e.Uri);
                    if (!allowed)
                    {
                        e.Cancel = true;
                        if (tab.Trusted && AllowedWebsite(e.Uri)) Open(e.Uri, true);
                        else status.Text = "This navigation cannot open inside SceneTrace.";
                        return;
                    }
                    tab.Loading = true;
                    tab.Started = Stopwatch.GetTimestamp();
                    UpdateChrome(tab);
                };
                core.FrameNavigationStarting += (s, e) => {
                    if (!tab.Trusted && !AllowedWebsite(e.Uri) && e.Uri != "about:blank" && !e.Uri.StartsWith("about:srcdoc") && !e.Uri.StartsWith("blob:https://") && !e.Uri.StartsWith("data:")) e.Cancel = true;
                };
                core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
                core.WebResourceRequested += (s, e) => {
                    if (!tab.Trusted && BlockResource(tab, e.Request.Uri, e.ResourceContext)) { e.Response = environment.CreateWebResourceResponse(new MemoryStream(), 403, "Blocked by SceneTrace protection", "Content-Type: text/plain"); return; }
                    if (!tab.Trusted && IsLocalResource(e.Request.Uri))
                        e.Response = environment.CreateWebResourceResponse(new MemoryStream(), 403, "Local access blocked", "Content-Type: text/plain");
                };
                core.NavigationCompleted += async (s, e) => {
                    tab.Loading = false;
                    if (!tab.Trusted && e.IsSuccess) { await ApplyCosmeticFilters(tab); await ScanMedia(tab); }
                    if (tab.Closed) return;
                    tab.Page.Text = tab.Trusted ? "SceneTrace" : ShortTitle(core.DocumentTitle);
                    UpdateChrome(tab);
                    if (!e.IsSuccess) status.Text = "The page could not load (" + e.WebErrorStatus + "). Refresh or open it externally.";
                    else if (!tab.Trusted && AllowedWebsite(core.Source))
                    {
                        try { await Post("desktop/event", new { action = "navigation", url = core.Source, title = core.DocumentTitle }); }
                        catch { status.Text = "Page loaded. Browsing history could not be saved."; }
                    }
                };
                core.DocumentTitleChanged += (s, e) => { if (!tab.Closed && !tab.Trusted) tab.Page.Text = ShortTitle(core.DocumentTitle); };
                core.SourceChanged += (s, e) => UpdateChrome(tab);
                core.ProcessFailed += (s, e) => { status.Text = "This browser tab stopped. Press Refresh to restore it."; tab.Loading = false; };
                if (tab.Trusted) core.WebMessageReceived += ReceiveMessage;
                if (navigate) core.Navigate(tab.Pending);
            }
            catch { view.Dispose(); tab.View = null; throw; }
            finally { tab.Creating = false; }
        }

        private static string ShortTitle(string value) => String.IsNullOrEmpty(value) ? "Website" : value.Length > 26 ? value.Substring(0, 25) + "…" : value;

        private bool IsApp(string value)
        {
            return Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.GetLeftPart(UriPartial.Authority) == appOrigin;
        }

        private static bool IsLocalResource(string value)
        {
            if (!Uri.TryCreate(value, UriKind.Absolute, out var uri)) return true;
            if (uri.Scheme == "file" || uri.Scheme == "ftp") return true;
            if (uri.Scheme != "http" && uri.Scheme != "https") return false;
            if (uri.IsLoopback || uri.Host.EndsWith(".localhost") || uri.Host.EndsWith(".local") || uri.Host.EndsWith(".internal")) return true;
            if (!IPAddress.TryParse(uri.Host.Trim('[', ']'), out var ip)) return false;
            if (ip.IsIPv4MappedToIPv6) ip = ip.MapToIPv4();
            var b = ip.GetAddressBytes();
            return IPAddress.IsLoopback(ip) || ip.IsIPv6LinkLocal || ip.IsIPv6SiteLocal ||
                   (b.Length == 16 && (b[0] & 0xfe) == 0xfc) ||
                   (b.Length == 4 && (b[0] == 0 || b[0] == 10 || b[0] == 127 || b[0] >= 224 ||
                    (b[0] == 169 && b[1] == 254) || (b[0] == 192 && b[1] == 168) || (b[0] == 172 && b[1] >= 16 && b[1] <= 31)));
        }

        private static bool AllowedWebsite(string value)
        {
            return Uri.TryCreate(value, UriKind.Absolute, out var uri) && (uri.Scheme == "https" || uri.Scheme == "http") &&
                   String.IsNullOrEmpty(uri.UserInfo) && !IsLocalResource(value);
        }

        private void UpdateChrome(BrowserTab tab)
        {
            if (tab != Current || tab.Closed) return;
            address.Text = tab.Trusted ? "" : tab.View?.CoreWebView2?.Source ?? tab.Pending;
            progress.Visible = tab.Loading;
            UpdateDetector();
            UpdateShieldChrome();
            status.Text = tab.Trusted ? "SceneTrace · private on this PC" : tab.Loading ? "Loading website…" : address.Text;
        }

        private void NavigateAddress()
        {
            var value = address.Text.Trim();
            if (!value.Contains("://")) value = "https://" + value;
            if (!AllowedWebsite(value)) { status.Text = "Enter a public website address."; return; }
            if (Current == null || Current.Trusted) Open(value, true);
            else if (Current.View?.CoreWebView2 != null) Current.View.CoreWebView2.Navigate(value);
        }

        private void Reload()
        {
            if (Current?.View?.CoreWebView2 == null) return;
            try { Current.View.Reload(); }
            catch
            {
                var tab = Current;
                tab.Pending = tab.View.Source?.AbsoluteUri ?? tab.Pending;
                tab.View.Dispose();
                tab.View = null;
                _ = EnsureTab(tab);
            }
        }

        private async Task FindText()
        {
            if (Current?.View?.CoreWebView2 == null || String.IsNullOrEmpty(find.Text)) return;
            try { await Current.View.CoreWebView2.ExecuteScriptAsync("window.find(" + json.Serialize(find.Text) + ")"); }
            catch { status.Text = "Find is unavailable until this page finishes loading."; }
        }

        private void SelectApp(string section)
        {
            if (appTab?.View?.CoreWebView2 == null) return;
            tabs.SelectedTab = appTab.Page;
            appTab.View.CoreWebView2.Navigate(appOrigin + "/#" + section);
        }

        private void SendToApp(string action, string value = null)
        {
            var current = Current;
            value = value ?? current?.View?.CoreWebView2?.Source ?? current?.Pending;
            if (action != "deep-all" && !AllowedWebsite(value)) { status.Text = "Open a website first."; return; }
            var title = current?.View?.CoreWebView2?.DocumentTitle ?? value;
            tabs.SelectedTab = appTab.Page;
            appTab.View.CoreWebView2.PostWebMessageAsJson(json.Serialize(new { action, url = value, title }));
        }

        private void ReceiveMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (!IsApp(e.Source)) return;
            try
            {
                var data = json.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
                if (!data.TryGetValue("action", out var action)) return;
                var value = data.TryGetValue("url", out var requested) ? requested as string : null;
                if ((string)action == "open" && AllowedWebsite(value)) Open(value, true);
                if ((string)action == "external" && AllowedWebsite(value)) Process.Start(new ProcessStartInfo(value) { UseShellExecute = true });
            }
            catch (Exception) { status.Text = "The browser action could not be completed."; }
        }

        private async void Bookmark()
        {
            var current = Current?.View?.CoreWebView2;
            if (current == null || !AllowedWebsite(current.Source)) return;
            try { await Post("browser/bookmark", new { url = current.Source, title = current.DocumentTitle }); status.Text = "Bookmark saved."; }
            catch { status.Text = "Bookmark could not be saved."; }
        }

        private void OpenExternal()
        {
            var value = Current?.View?.CoreWebView2?.Source ?? Current?.Pending;
            if (AllowedWebsite(value)) Process.Start(new ProcessStartInfo(value) { UseShellExecute = true });
        }

        private void CloseTab(BrowserTab tab)
        {
            if (tab == null || tab.Trusted) return;
            if (nativeTransfers.Values.Any(t=>t.Tab==tab && (t.Operation.State==CoreWebView2DownloadState.InProgress || t.Operation.CanResume)))
            {
                tab.DownloadOnly=true;
                tabs.TabPages.Remove(tab.Page);
                status.Text="Tab closed. Its download continues in Download Center.";
                return;
            }
            DisposeTab(tab);
            openTabs.Remove(tab);
            tabs.TabPages.Remove(tab.Page);
            tab.Page.Dispose();
        }

        private void DisposeTab(BrowserTab tab)
        {
            tab.Closed = true;
            detected.Remove(tab); videoElements.Remove(tab); blockedRequests.Remove(tab); scanning.Remove(tab);
            tab.View?.Dispose();
            tab.View = null;
        }

        private async Task<string> Post(string path, object value)
        {
            using (var body = new StringContent(json.Serialize(value), System.Text.Encoding.UTF8, "application/json"))
            using (var reply = await client.PostAsync(appOrigin + "/api/" + path, body))
            {
                reply.EnsureSuccessStatusCode();
                return await reply.Content.ReadAsStringAsync();
            }
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == (Keys.Control | Keys.L)) { address.Focus(); address.SelectAll(); return true; }
            if (keyData == (Keys.Control | Keys.F)) { find.Visible=true;find.Focus(); find.SelectAll(); return true; }
            if (keyData == (Keys.Control | Keys.W)) { CloseTab(Current); return true; }
            if (keyData == (Keys.Control | Keys.T)) { Open("https://www.wikipedia.org/", true); return true; }
            if (keyData == Keys.F5) { Reload(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }
    }
}
