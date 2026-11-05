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
        internal TabPage Page;
        internal WebView2 View;
        internal string Pending;
        internal bool Trusted;
        internal bool Loading;
        internal bool Creating;
        internal bool Closed;
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
        private readonly TabControl tabs = new TabControl { Dock = DockStyle.Fill };
        private readonly ToolStrip tools = new ToolStrip { GripStyle = ToolStripGripStyle.Hidden, Dock = DockStyle.Top };
        private readonly ToolStripTextBox address = new ToolStripTextBox { AutoSize = false, Width = 390 };
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
            Size = new Size(1260, 840);
            MinimumSize = new Size(800, 600);
            BackColor = Color.FromArgb(19, 25, 34);
            ForeColor = Color.White;
            tools.BackColor = BackColor;
            tools.ForeColor = ForeColor;
            tools.RenderMode = ToolStripRenderMode.System;
            AddButton("Home", () => SelectApp("home"));
            AddButton("←", () => { if (Current?.View?.CoreWebView2?.CanGoBack == true) Current.View.GoBack(); }, "Back");
            AddButton("→", () => { if (Current?.View?.CoreWebView2?.CanGoForward == true) Current.View.GoForward(); }, "Forward");
            AddButton("↻", Reload, "Refresh page");
            tools.Items.Add(address);
            address.AccessibleName = "Website address";
            address.KeyDown += (s, e) => { if (e.KeyCode == Keys.Enter) { NavigateAddress(); e.SuppressKeyPress = true; } };
            AddButton("Go", NavigateAddress);
            AddButton("+", () => Open("https://www.wikipedia.org/", true), "New tab");
            AddButton("×", () => CloseTab(Current), "Close tab");
            AddButton("☆", Bookmark, "Bookmark page");
            var actions = new ToolStripDropDownButton("Search & video");
            AddMenu(actions, "Quick search this website", () => SendToApp("quick-site"));
            AddMenu(actions, "Deep search this website", () => SendToApp("deep-site"));
            AddMenu(actions, "Deep search all sources", () => SendToApp("deep-all"));
            AddMenu(actions, "Add website as source", () => SendToApp("add-source"));
            AddMenu(actions, "Inspect current video", () => SendToApp("inspect"));
            AddMenu(actions, "Save current page", () => SendToApp("save-page"));
            AddMenu(actions, "Open in external browser", OpenExternal);
            tools.Items.Add(actions);
            AddButton("↓", () => SelectApp("downloads"), "Download Center");
            AddMenu(actions, "Browser downloads / Save As", () => Current?.View?.CoreWebView2?.OpenDefaultDownloadDialog());
            tools.Items.Add(find);
            find.AccessibleName = "Find text on page";
            find.KeyDown += async (s, e) => { if (e.KeyCode == Keys.Enter) { await FindText(); e.SuppressKeyPress = true; } };
            AddButton("Find", async () => await FindText());
            var bar = new StatusStrip();
            bar.Items.Add(status);
            bar.Items.Add(progress);
            Controls.Add(tabs);
            Controls.Add(tools);
            Controls.Add(bar);
            tabs.SelectedIndexChanged += async (s, e) => {
                try { await ActivateTab(); }
                catch (Exception) { status.Text = "This tab could not start. Refresh or open it externally."; }
            };
            tabs.MouseDown += (s, e) => {
                if (e.Button != MouseButtons.Middle) return;
                for (int i = 0; i < tabs.TabCount; i++)
                    if (tabs.GetTabRect(i).Contains(e.Location)) { CloseTab((BrowserTab)tabs.TabPages[i].Tag); break; }
            };
            client.DefaultRequestHeaders.Add("X-SceneTrace", "local");
            client.DefaultRequestHeaders.Add("X-SceneTrace-Desktop", Environment.GetEnvironmentVariable("SCENETRACE_DESKTOP_TOKEN"));
            client.Timeout = TimeSpan.FromSeconds(15);
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
                environment = await CoreWebView2Environment.CreateAsync(null, profile);
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
            var tab = new BrowserTab { Pending = value, Trusted = trusted, Page = new TabPage(trusted ? "SceneTrace" : "New tab") };
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

        private async Task EnsureTab(BrowserTab tab)
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
                core.NewWindowRequested += (s, e) => { e.Handled = true; Open(e.Uri, true); };
                core.PermissionRequested += (s, e) => { e.State = CoreWebView2PermissionState.Deny; };
                core.DownloadStarting += (s, e) => TrackDownload(tab, e);
                core.NavigationStarting += (s, e) => {
                    bool allowed = tab.Trusted ? IsApp(e.Uri) : AllowedWebsite(e.Uri);
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
                    if (!tab.Trusted && IsLocalResource(e.Request.Uri))
                        e.Response = environment.CreateWebResourceResponse(new MemoryStream(), 403, "Local access blocked", "Content-Type: text/plain");
                };
                core.NavigationCompleted += async (s, e) => {
                    tab.Loading = false;
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
                core.Navigate(tab.Pending);
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
            DisposeTab(tab);
            openTabs.Remove(tab);
            tabs.TabPages.Remove(tab.Page);
            tab.Page.Dispose();
        }

        private void DisposeTab(BrowserTab tab)
        {
            tab.Closed = true;
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
            if (keyData == (Keys.Control | Keys.F)) { find.Focus(); find.SelectAll(); return true; }
            if (keyData == (Keys.Control | Keys.W)) { CloseTab(Current); return true; }
            if (keyData == (Keys.Control | Keys.T)) { Open("https://www.wikipedia.org/", true); return true; }
            if (keyData == Keys.F5) { Reload(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }
    }
}
