using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed partial class BrowserWindow
    {
        private HashSet<string> adDomains = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> shieldAllowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<BrowserTab,int> blockedRequests = new Dictionary<BrowserTab,int>();
        private readonly Queue<string> blockedHosts = new Queue<string>();
        private bool shieldDefault = true;
        private bool updatingFilters;
        private string filterStatus = "Bundled HaGeZi Light";
        private long filterTicks;
        private long filterDecisions;
        private readonly ToolStripDropDownButton shield = new ToolStripDropDownButton("◇") { AccessibleName="Website protection", ToolTipText="Ad and tracker protection" };
        private const string FilterUrl = "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/light.txt";

        private static HashSet<string> ParseFilters(string raw)
        {
            var set=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(var line in raw.Split('\n'))
            {
                var text=line.Trim();
                if(text.StartsWith("||") && text.EndsWith("^"))
                {
                    var host=text.Substring(2,text.Length-3);
                    if(host.Length<=253 && Regex.IsMatch(host,@"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9-]{2,63}$",RegexOptions.IgnoreCase)) set.Add(host);
                }
            }
            if(set.Count<1000)throw new InvalidDataException("The provider returned no valid domain filter list. The previous list is still active.");
            return set;
        }
        private void SetupShield()
        {
            tools.Items.Add(shield);
            try
            {
                using(var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("SceneTrace.Browser.Filters.light.txt.gz.b64"))
                using(var reader=new StreamReader(resource))
                using(var packed=new MemoryStream(Convert.FromBase64String(reader.ReadToEnd())))
                using(var gzip=new GZipStream(packed,CompressionMode.Decompress))
                using(var text=new StreamReader(gzip)) adDomains=ParseFilters(text.ReadToEnd());
                var cached=Path.Combine(profile,"shield-rules.txt");
                if(File.Exists(cached) && new FileInfo(cached).Length<8388608)
                {adDomains=ParseFilters(File.ReadAllText(cached));filterStatus="Updated "+File.GetLastWriteTime(cached).ToShortDateString();}
            }
            catch(Exception){filterStatus="Filter cache unavailable; update the lists";}
            try
            {
                var data=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(profile,"shield-settings.json")));
                shieldDefault=(bool)data["enabled"];
                foreach(string host in (System.Collections.IEnumerable)data["allowed"])shieldAllowed.Add(host);
            }
            catch(Exception){}
            shield.DropDownOpening+=(s,e)=>BuildShieldMenu();
        }
        private bool ShieldEnabled(BrowserTab tab)
        {
            return tab!=null&&!tab.Trusted&&shieldDefault&&Uri.TryCreate(tab.View?.CoreWebView2?.Source??tab.Pending,UriKind.Absolute,out var uri)&&!shieldAllowed.Contains(uri.Host);
        }
        private bool IsAdDomain(string host)
        {
            while(host.Contains(".")){if(adDomains.Contains(host))return true;host=host.Substring(host.IndexOf('.')+1);}return false;
        }
        private bool BlockResource(BrowserTab tab,string value,CoreWebView2WebResourceContext context)
        {
            long start=Stopwatch.GetTimestamp();
            try
            {
                // User navigation and native file transfers are never intercepted here.
                // Preserve media transport; block the ad/tracker loaders instead.
                if(!ShieldEnabled(tab)||context==CoreWebView2WebResourceContext.Document||context==CoreWebView2WebResourceContext.Media)return false;
                if(!Uri.TryCreate(value,UriKind.Absolute,out var uri)||!IsAdDomain(uri.Host))return false;
                blockedRequests[tab]=(blockedRequests.TryGetValue(tab,out int count)?count:0)+1;
                blockedHosts.Enqueue(uri.Host);while(blockedHosts.Count>20)blockedHosts.Dequeue();
                if(tab==Current)shield.Text="◇ "+blockedRequests[tab];
                return true;
            }
            finally{filterTicks+=Stopwatch.GetTimestamp()-start;filterDecisions++;}
        }
        private bool BlockPopup(BrowserTab tab,CoreWebView2NewWindowRequestedEventArgs e)
        {
            if(!ShieldEnabled(tab)||e.IsUserInitiated||!Uri.TryCreate(e.Uri,UriKind.Absolute,out var uri)||!IsAdDomain(uri.Host))return false;
            blockedRequests[tab]=(blockedRequests.TryGetValue(tab,out int count)?count:0)+1;
            status.Text="Advertising popup blocked. Use the shield to allow this site.";return true;
        }
        private void SaveShieldSettings()
        {
            Directory.CreateDirectory(profile);
            var path=Path.Combine(profile,"shield-settings.json");var temp=path+".new";
            File.WriteAllText(temp,json.Serialize(new { enabled=shieldDefault,allowed=shieldAllowed.ToArray() }));
            if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
        }
        private void BuildShieldMenu()
        {
            shield.DropDownItems.Clear();var tab=Current;
            var enabled=new ToolStripMenuItem("Protection enabled globally"){Checked=shieldDefault};
            enabled.Click+=(s,e)=>{shieldDefault=!shieldDefault;SaveShieldSettings();UpdateShieldChrome();Reload();};shield.DropDownItems.Add(enabled);
            if(tab!=null&&!tab.Trusted&&Uri.TryCreate(tab.View?.CoreWebView2?.Source??tab.Pending,UriKind.Absolute,out var uri))
            {
                var site=new ToolStripMenuItem("Allow ads and trackers on "+uri.Host){Checked=shieldAllowed.Contains(uri.Host)};
                site.Click+=(s,e)=>{if(!shieldAllowed.Add(uri.Host))shieldAllowed.Remove(uri.Host);SaveShieldSettings();UpdateShieldChrome();Reload();};shield.DropDownItems.Add(site);
            }
            shield.DropDownItems.Add("Blocked on this page: "+(tab!=null&&blockedRequests.TryGetValue(tab,out int count)?count:0)).Enabled=false;
            shield.DropDownItems.Add(adDomains.Count.ToString("N0")+" domain rules · "+filterStatus).Enabled=false;
            shield.DropDownItems.Add("Ads and trackers use the same domain list").Enabled=false;
            shield.DropDownItems.Add("Update filter list",null,async(s,e)=>await UpdateFilters());
            var recent=new ToolStripMenuItem("Recently blocked domains");foreach(var host in blockedHosts.Distinct())recent.DropDownItems.Add(host).Enabled=false;shield.DropDownItems.Add(recent);
        }
        private void UpdateShieldChrome()
        {
            shield.Text=ShieldEnabled(Current)?"◇ "+(Current!=null&&blockedRequests.TryGetValue(Current,out int count)?count:0):"◇ Off";
        }
        private async Task ApplyCosmeticFilters(BrowserTab tab)
        {
            if(tab.Trusted||tab.Closed)return;
            try{await tab.View.CoreWebView2.ExecuteScriptAsync("(()=>{const old=document.getElementById('__scenetrace_ad_style');if(old)old.remove();"+(ShieldEnabled(tab)?"const s=document.createElement('style');s.id='__scenetrace_ad_style';s.textContent='.adsbygoogle,iframe[src*=\"doubleclick.net\"]{display:none!important}';document.head.append(s);":"")+"})()");}catch(Exception){}
        }
        private async Task UpdateFilters()
        {
            if(updatingFilters)return;updatingFilters=true;status.Text="Updating ad and tracker rules…";
            try
            {
                string raw;
                using(var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false}){Timeout=TimeSpan.FromSeconds(30)})
                using(var response=await http.GetAsync(FilterUrl,HttpCompletionOption.ResponseHeadersRead))
                {
                    response.EnsureSuccessStatusCode();
                    using(var input=await response.Content.ReadAsStreamAsync())
                    using(var output=new MemoryStream())
                    {var buffer=new byte[65536];int length;while((length=await input.ReadAsync(buffer,0,buffer.Length))>0){if(output.Length+length>8388608)throw new InvalidDataException("Filter update is unexpectedly large.");output.Write(buffer,0,length);}raw=Encoding.UTF8.GetString(output.ToArray());}
                }
                var replacement=await Task.Run(()=>ParseFilters(raw));
                string file=Path.Combine(profile,"shield-rules.txt"),temp=file+".new";
                File.WriteAllText(temp,raw);if(File.Exists(file))File.Replace(temp,file,null);else File.Move(temp,file);
                adDomains=replacement;filterStatus="Updated "+DateTime.Now.ToShortDateString();status.Text="Protection updated: "+adDomains.Count.ToString("N0")+" domain rules.";
            }
            catch(Exception){status.Text="Filter update failed. The existing rules remain active; check your connection and retry.";}
            finally{updatingFilters=false;}
        }
    }
}
