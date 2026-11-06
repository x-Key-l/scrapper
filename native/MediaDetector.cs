using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed class DetectedMedia
    {
        public string Url;
        public string Title;
        public string Kind;
        public bool Advertisement;
    }
    internal sealed partial class BrowserWindow
    {
        private readonly Dictionary<BrowserTab, Dictionary<string, DetectedMedia>> detected = new Dictionary<BrowserTab, Dictionary<string, DetectedMedia>>();
        private readonly HashSet<BrowserTab> videoElements = new HashSet<BrowserTab>();
        private readonly ToolStripDropDownButton detector = new ToolStripDropDownButton("↓ Video") { ToolTipText = "Detect video and inspect download formats", AccessibleName = "Video detector" };
        private readonly HashSet<BrowserTab> scanning = new HashSet<BrowserTab>();

        private void SetupDetector()
        {
            tools.Items.Add(detector);
            detector.DropDownOpening += (s,e) => BuildDetectorMenu();
        }
        private Dictionary<string, DetectedMedia> MediaFor(BrowserTab tab)
        {
            if (!detected.TryGetValue(tab,out var items)) detected[tab] = items = new Dictionary<string, DetectedMedia>();
            return items;
        }
        private void AddMedia(BrowserTab tab, string value, string title, string kind, bool advertisement = false)
        {
            if (tab.Trusted || tab.Closed || !AllowedWebsite(value)) return;
            var items = MediaFor(tab);
            // Bounded observations, not a full network log. Actual downloads have no size limit.
            if (items.Count >= 128 && !items.ContainsKey(value)) return;
            items[value] = new DetectedMedia { Url=value,Title=String.IsNullOrWhiteSpace(title)?"Detected media":title,Kind=kind,Advertisement=advertisement };
            UpdateDetector();
        }
        private void ObserveMedia(BrowserTab tab, CoreWebView2WebResourceResponseReceivedEventArgs e)
        {
            if (tab.Trusted || tab.Closed || e.Response.StatusCode < 200 || e.Response.StatusCode >= 300) return;
            try
            {
                var value = e.Request.Uri;
                if (!Uri.TryCreate(value,UriKind.Absolute,out var uri)) return;
                string ext=Path.GetExtension(uri.AbsolutePath).ToLowerInvariant();
                // Segment requests are pieces, not independent videos or reported qualities.
                if (new[]{".ts",".m4s",".cmfv",".cmfa"}.Contains(ext)) return;
                string mime=e.Response.Headers.Contains("Content-Type")?e.Response.Headers.GetHeader("Content-Type").Split(';')[0].Trim().ToLowerInvariant():"";
                bool manifest=ext==".m3u8"||ext==".mpd"||mime.Contains("mpegurl")||mime=="application/dash+xml";
                if (manifest || mime.StartsWith("video/") || mime.StartsWith("audio/"))
                    AddMedia(tab,value,tab.View.CoreWebView2.DocumentTitle,manifest?"Adaptive stream":"Media response", IsAdDomain(uri.Host));
            }
            catch (Exception) { /* Metadata inspection must not interrupt a response. */ }
        }
        private async Task ScanMedia(BrowserTab tab)
        {
            if (tab==null||tab.Trusted||tab.Closed||tab.View?.CoreWebView2==null||!scanning.Add(tab)) return;
            try
            {
                var script=@"(()=>{
                    const items=[], title=document.title, seen=new Set();
                    const add=(url,label,kind,ad=false)=>{try{const u=new URL(url,location.href);if(!/^https?:$/.test(u.protocol)||seen.has(u.href))return;seen.add(u.href);items.push({url:u.href,title:label||title,kind,ad});}catch{}};
                    const media=[...document.querySelectorAll('video,audio')].slice(0,64);
                    for(const v of media){const ad=!!v.closest('.adsbygoogle,[class*=advert],[id*=advert]');const chosen=v.currentSrc||v.src||v.querySelector('source')?.src;if(chosen)add(chosen,title,'HTML media',ad);}
                    for(const a of [...document.querySelectorAll('a[download]')].slice(0,64))if(/\.(mp4|m4v|webm|mkv|mov|avi|mp3|m4a|ogg|opus|flac|wav|m3u8|mpd)(?:$|[?#])/i.test(a.href))add(a.href,a.textContent.trim()||title,'Website download');
                    for(const m of document.querySelectorAll('meta[property=""og:video""],meta[property=""og:video:url""],meta[property=""og:video:secure_url""]'))add(m.content,title,'Video metadata');
                    let visited=0;const walk=x=>{if(!x||typeof x!=='object'||visited++>64)return;if(Array.isArray(x))return x.slice(0,20).forEach(walk);if(x['@type']==='VideoObject'&&x.contentUrl)add(x.contentUrl,x.name,'Structured video');if(x['@graph'])walk(x['@graph']);};
                    for(const s of [...document.querySelectorAll('script[type=""application/ld+json""]')].slice(0,10)){if(s.textContent.length<262144)try{walk(JSON.parse(s.textContent));}catch{}}
                    return {hasVideo:media.length>0,items};
                })()";
                var data=json.Deserialize<Dictionary<string,object>>(await tab.View.CoreWebView2.ExecuteScriptAsync(script));
                if ((bool)data["hasVideo"]) videoElements.Add(tab);
                foreach(Dictionary<string,object> item in (IEnumerable)data["items"])
                    AddMedia(tab,(string)item["url"],(string)item["title"],(string)item["kind"],(bool)item["ad"]);
                UpdateDetector();
            }
            catch(Exception) { if(tab==Current)status.Text="Video inspection is unavailable on this page. Its ordinary download buttons still work."; }
            finally { scanning.Remove(tab); }
        }
        private void UpdateDetector()
        {
            var tab=Current;
            int count=tab!=null&&detected.TryGetValue(tab,out var items)?items.Values.Count(x=>!x.Advertisement):0;
            detector.Text=count>0?"↓ "+count:"↓ Video";
            detector.ToolTipText=count>0?"Media detected: "+count:tab!=null&&videoElements.Contains(tab)?"Video detected. No compatible download found.":"Inspect this page for video";
        }
        private void BuildDetectorMenu()
        {
            detector.DropDownItems.Clear();
            var tab=Current;
            if(tab==null||tab.Trusted){detector.DropDownItems.Add("Open a website to detect videos").Enabled=false;return;}
            var items=MediaFor(tab).Values.OrderBy(x=>x.Advertisement).ToArray();
            detector.DropDownItems.Add(items.Length>0?"Media detected: "+items.Length:videoElements.Contains(tab)?"Video detected. No compatible download found.":"No media detected yet").Enabled=false;
            foreach(var item in items)
            {
                var menu=new ToolStripMenuItem((item.Advertisement?"Possible advertisement · ":"")+ShortMediaTitle(item.Title)+" · "+item.Kind);
                menu.DropDownItems.Add("Inspect available formats…",null,async(s,e)=>await ShowDetectedFormats(tab,item,menu));
                menu.DropDownItems.Add("Open media address",null,(s,e)=>Open(item.Url,true));
                detector.DropDownItems.Add(menu);
            }
            detector.DropDownItems.Add(new ToolStripSeparator());
            detector.DropDownItems.Add("Rescan current page",null,async(s,e)=>{await ScanMedia(tab);detector.ShowDropDown();});
            detector.DropDownItems.Add("Analyze original video page",null,(s,e)=>SendToApp("inspect",tab.View.CoreWebView2.Source));
            detector.DropDownItems.Add("Save page",null,(s,e)=>SendToApp("save-page",tab.View.CoreWebView2.Source));
            detector.DropDownItems.Add("Browser downloads / Save As",null,(s,e)=>tab.View.CoreWebView2.OpenDefaultDownloadDialog());
        }
        private static string ShortMediaTitle(string value) => value.Length>65?value.Substring(0,62)+"…":value;
        private async Task ShowDetectedFormats(BrowserTab tab, DetectedMedia item, ToolStripMenuItem parent)
        {
            status.Text="Checking formats for "+ShortMediaTitle(item.Title)+"…";
            try
            {
                var result=json.Deserialize<Dictionary<string,object>>(await Post("analyze",new { url=item.Url }));
                var formats=((IEnumerable)result["formats"]).Cast<Dictionary<string,object>>().ToArray();
                using(var dialog=new Form {Text="Download detected media",Width=520,Height=310,StartPosition=FormStartPosition.CenterParent,BackColor=BackColor,ForeColor=ForeColor,Font=Font,MinimizeBox=false,MaximizeBox=false})
                {
                    var layout=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(18),ColumnCount=1,RowCount=6};dialog.Controls.Add(layout);
                    layout.Controls.Add(new Label{Text=ShortMediaTitle(item.Title),AutoSize=true});
                    if(formats.Length==0)
                    {
                        layout.Controls.Add(new Label{Text="Video detected. No compatible download found.\n"+(result.TryGetValue("notice",out var notice)?notice:""),AutoSize=true,MaximumSize=new System.Drawing.Size(460,0)});
                        var original=new Button{Text="Open original page",AutoSize=true};original.Click+=(s,e)=>{dialog.Close();tabs.SelectedTab=tab.Page;};layout.Controls.Add(original);dialog.ShowDialog(this);return;
                    }
                    var choices=new ComboBox{DropDownStyle=ComboBoxStyle.DropDownList,Dock=DockStyle.Fill};
                    foreach(var format in formats)choices.Items.Add((format.TryGetValue("height",out var height)&&height!=null?height+"p · ":"")+format["ext"]+" · "+format["label"]);
                    choices.SelectedIndex=0;layout.Controls.Add(choices);
                    string folder=downloadFolder;
                    var folderLabel=new Label{Text=folder,AutoSize=true,MaximumSize=new System.Drawing.Size(460,0)};layout.Controls.Add(folderLabel);
                    var choose=new Button{Text="Choose folder…",AutoSize=true};choose.Click+=(s,e)=>{using(var picker=new FolderBrowserDialog{SelectedPath=folder})if(picker.ShowDialog(dialog)==DialogResult.OK){folder=picker.SelectedPath;folderLabel.Text=folder;}};layout.Controls.Add(choose);
                    var start=new Button{Text="Download",AutoSize=true};layout.Controls.Add(start);
                    start.Click+=async(s,e)=>{start.Enabled=false;try{await Post("download/add",new {analysis_id=result["analysis_id"],format_id=formats[choices.SelectedIndex]["id"],destination=folder});dialog.Close();SelectApp("downloads");}catch(Exception){MessageBox.Show(dialog,"The transfer could not start. Refresh this video or choose another folder.");start.Enabled=true;}};
                    dialog.ShowDialog(this);
                }
            }
            catch(Exception){status.Text="Could not inspect this media. Use Analyze original video page or the website's download button.";}
        }
    }
}
