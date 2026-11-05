using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace SceneTrace
{
    internal sealed class NativeTransfer
    {
        internal string Id = Guid.NewGuid().ToString("N");
        internal CoreWebView2DownloadOperation Operation;
        internal BrowserTab Tab;
        internal string Source;
        internal bool Dirty = true;
        internal long PreviousBytes;
        internal DateTime PreviousTime = DateTime.UtcNow;
    }

    internal sealed partial class BrowserWindow
    {
        private readonly Dictionary<string, NativeTransfer> nativeTransfers = new Dictionary<string, NativeTransfer>();
        private bool syncingDownloads;
        private string downloadFolder;
        private bool sourceFolders = true;
        private DateTime settingsChecked = DateTime.MinValue;

        private static string FileComponent(string value)
        {
            foreach (char c in Path.GetInvalidFileNameChars()) value = value.Replace(c, '_');
            value = value.Trim(' ', '.');
            return String.IsNullOrEmpty(value) ? "Website" : value;
        }

        private void TrackDownload(BrowserTab tab, CoreWebView2DownloadStartingEventArgs args)
        {
            // Native download UI owns Save As, destination changes, pause/cancel and
            // overwrite confirmation. Analysis is never a prerequisite for a file.
            if (!String.IsNullOrEmpty(downloadFolder))
            {
                try
                {
                    string folder = downloadFolder;
                    if (sourceFolders && Uri.TryCreate(tab.View.CoreWebView2.Source, UriKind.Absolute, out var source))
                        folder = Path.Combine(folder, FileComponent(source.Host.StartsWith("www.")?source.Host.Substring(4):source.Host));
                    Directory.CreateDirectory(folder);
                    string name = Path.GetFileName(args.ResultFilePath);
                    string candidate = Path.Combine(folder, name);
                    int number = 1;
                    while (File.Exists(candidate)) candidate = Path.Combine(folder, Path.GetFileNameWithoutExtension(name) + " (" + number++ + ")" + Path.GetExtension(name));
                    args.ResultFilePath = candidate;
                }
                catch (Exception) { status.Text = "The preferred folder is unavailable. Choose another folder in the browser download dialog."; }
            }
            var transfer = new NativeTransfer { Operation = args.DownloadOperation, Tab = tab, Source = tab.View.CoreWebView2.Source };
            nativeTransfers[transfer.Id] = transfer;
            transfer.Operation.BytesReceivedChanged += (s, e) => transfer.Dirty = true;
            transfer.Operation.StateChanged += (s, e) => {
                transfer.Dirty = true;
                if (transfer.Operation.State == CoreWebView2DownloadState.Completed)
                    status.Text = "Download complete: " + Path.GetFileName(transfer.Operation.ResultFilePath);
                else if (transfer.Operation.State == CoreWebView2DownloadState.Interrupted)
                    status.Text = "Download: " + transfer.Operation.InterruptReason + ". Open Downloads for details.";
            };
            status.Text = "Download started: " + Path.GetFileName(args.ResultFilePath);
            qaDownloadStarting?.Invoke(tab,args);
        }

        private async Task PumpDownloads()
        {
            if (syncingDownloads || closing) return;
            syncingDownloads = true;
            var pending = new List<NativeTransfer>();
            try
            {
                if ((DateTime.UtcNow-settingsChecked).TotalSeconds > 10)
                {
                    var settings = json.Deserialize<Dictionary<string, object>>(await Post("desktop/download-settings", new { }));
                    downloadFolder = (string)settings["destination"];
                    sourceFolders = (bool)settings["organize_by_source"];
                    settingsChecked = DateTime.UtcNow;
                }
                if (nativeTransfers.Count == 0) return;
                var updates = new List<object>();
                foreach (var transfer in nativeTransfers.Values.ToArray())
                {
                    if (!transfer.Dirty) continue;
                    var op = transfer.Operation;
                    string reason = op.InterruptReason.ToString();
                    string state = op.State == CoreWebView2DownloadState.Completed ? "completed" :
                        op.State == CoreWebView2DownloadState.InProgress ? "downloading" :
                        reason == "UserPaused" ? "paused" : reason == "UserCanceled" ? "cancelled" : "failed";
                    double seconds = Math.Max(.01,(DateTime.UtcNow-transfer.PreviousTime).TotalSeconds);
                    double speed = Math.Max(0,(op.BytesReceived-transfer.PreviousBytes)/seconds);
                    long? total = op.TotalBytesToReceive.HasValue ? (long?)checked((long)op.TotalBytesToReceive.Value) : null;
                    if (total <= 0) total = null;
                    updates.Add(new { id = transfer.Id, title = Path.GetFileName(op.ResultFilePath), source = transfer.Source,
                        path = op.ResultFilePath, status = state, bytes = op.BytesReceived, total, speed = state == "downloading" ? (double?)speed : null,
                        eta = speed > 0 && total.HasValue ? (double?)Math.Max(0,(total.Value-op.BytesReceived)/speed) : null,
                        can_resume = op.CanResume, failure = state == "failed" ? reason : "",
                        error = state == "failed" ? "Browser download interrupted: " + reason + (op.CanResume ? ". Resume is available." : ". Open the source page and retry its download button.") : "" });
                    transfer.PreviousTime = DateTime.UtcNow;
                    transfer.PreviousBytes = op.BytesReceived;
                    transfer.Dirty = false;
                    pending.Add(transfer);
                }
                var response = json.Deserialize<Dictionary<string, object>>(await Post("desktop/downloads",new { updates }));
                foreach (var transfer in pending.Where(t=>t.Operation.State==CoreWebView2DownloadState.Completed || (t.Operation.State==CoreWebView2DownloadState.Interrupted && !t.Operation.CanResume)).ToArray())
                    nativeTransfers.Remove(transfer.Id);
                foreach (var tab in openTabs.Where(t=>t.DownloadOnly && !nativeTransfers.Values.Any(d=>d.Tab==t)).ToArray())
                {DisposeTab(tab);openTabs.Remove(tab);tab.Page.Dispose();}
                if (response.TryGetValue("commands", out var commands))
                {
                    foreach (Dictionary<string, object> command in (System.Collections.IEnumerable)commands)
                    {
                        if (!nativeTransfers.TryGetValue((string)command["id"], out var transfer)) continue;
                        string action = (string)command["action"];
                        if (action == "pause") transfer.Operation.Pause();
                        if (action == "cancel") transfer.Operation.Cancel();
                        if ((action == "resume" || action == "retry") && transfer.Operation.CanResume) transfer.Operation.Resume();
                        transfer.Dirty = true;
                    }
                }
            }
            catch (Exception)
            {
                foreach (var transfer in pending) transfer.Dirty = true;
                // Ordinary native UI and transfers remain operational if the app API fails.
            }
            finally { syncingDownloads = false; }
        }
    }
}
