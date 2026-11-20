package dev.scenetrace.browser

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.Message
import android.os.Parcel
import android.view.ViewGroup
import android.webkit.*
import java.io.ByteArrayInputStream
import java.util.zip.GZIPInputStream

/** The Activity owns this pool. Only the selected WebView is attached to its container. */
class BrowserViews(private val ui: BrowserActivity, private val store: BrowserStore) {
    private val live = LinkedHashMap<String, WebView>(4, 0.75f, true)
    private val snapshots = LinkedHashMap<String, Bundle>()
    private val pending = mutableMapOf<String, WebView>()
    private val handler = Handler(Looper.getMainLooper())
    private val rules = FilterBundle.get(ui)

    fun obtain(tab: Tab) = live[tab.id] ?: create(tab).also { web ->
        live[tab.id] = web
        val saved = snapshots.remove(tab.id)
        if ((saved == null || web.restoreState(saved) == null) && Addresses.host(tab.url) != null) web.loadUrl(tab.url)
        trim(3)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun create(tab: Tab): WebView {
        val web = WebView(ui)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            safeBrowsingEnabled = true
            setSupportMultipleWindows(true)
            javaScriptCanOpenWindowsAutomatically = true
            builtInZoomControls = true
            displayZoomControls = false
            useWideViewPort = true
            loadWithOverviewMode = true
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
        web.webViewClient = object : WebViewClient() {
            @Volatile private var site = Addresses.host(tab.url).orEmpty()
            private fun enabled() = store.protection && !store.allowed(site)
            private fun blocked(host: String?) = host != null && enabled() && rules.get().matches(host)
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = Addresses.host(request.url.toString()) ?: return true
                if (request.isForMainFrame && (request.isRedirect || !request.hasGesture()) && blocked(target)) {
                    if (ui.isActive(tab)) ui.notice("Advertising navigation blocked")
                    return true
                }
                return false
            }
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                if (!request.isForMainFrame && blocked(request.url.host)) {
                    return WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", emptyMap(), ByteArrayInputStream(byteArrayOf()))
                }
                return null
            }
            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                val host = Addresses.host(url) ?: return
                site = host
                if (tab.url != url) tab.title = ""
                tab.url = url
                ui.pageChanged(tab)
            }
            override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean) {
                if (Addresses.host(url) == null) return
                tab.url = url
                site = Addresses.host(url).orEmpty()
                // A back/forward-cache traversal can restore a document without another full load.
                view.copyBackForwardList().currentItem?.takeIf { it.url == url }?.title?.let {
                    tab.title = it.take(400)
                }
                ui.pageChanged(tab)
            }
            override fun onPageFinished(view: WebView, url: String) {
                if (Addresses.host(url) == null || view.url != url) return
                tab.url = url
                tab.title = view.title.orEmpty().take(400)
                store.savePage(Page(url, tab.title))
                ui.pageChanged(tab)
            }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && ui.isActive(tab)) ui.notice(error.description.toString())
            }
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                discard(tab.id, false)
                ui.rendererLost(tab)
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onReceivedTitle(view: WebView, title: String?) {
                if (view.url == tab.url && !title.isNullOrBlank()) {
                    tab.title = title.take(400)
                    ui.pageChanged(tab)
                }
            }
            override fun onProgressChanged(view: WebView, progress: Int) { if (ui.isActive(tab)) ui.showProgress(progress) }
            override fun onCreateWindow(view: WebView, dialog: Boolean, gesture: Boolean, result: Message): Boolean {
                if (!ui.isActive(tab) || pending.containsKey(tab.id)) return false
                val origin = Addresses.host(tab.url).orEmpty()
                val protected = store.protection && !store.allowed(origin)
                if (protected && !gesture) return false
                val probe = WebView(ui)
                pending[tab.id] = probe
                probe.settings.allowFileAccess = false
                probe.settings.allowContentAccess = false
                var handled = false
                fun route(url: String) {
                    if (handled || pending[tab.id] !== probe) return
                    val host = Addresses.host(url) ?: return
                    handled = true
                    handler.post {
                        if (pending[tab.id] !== probe) return@post
                        releasePopup(tab.id)
                        if (!ui.isActive(tab)) return@post
                        if (protected && rules.get().matches(host)) ui.notice("Advertising popup blocked") else ui.newTab(url)
                    }
                }
                probe.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                        if (request.isForMainFrame && request.method == "GET") route(request.url.toString())
                        return true
                    }
                    override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                        releasePopup(tab.id); return true
                    }
                }
                (result.obj as WebView.WebViewTransport).webView = probe
                result.sendToTarget()
                handler.postDelayed({ if (pending[tab.id] === probe) releasePopup(tab.id) }, 8000)
                return true
            }
        }
        web.setDownloadListener { url, agent, disposition, mime, length ->
            if (ui.isActive(tab)) {
                // Attachment navigations can start without replacing the visible document.
                web.copyBackForwardList().currentItem?.let { item ->
                    if (Addresses.host(item.url) != null) {
                        tab.url = item.url
                        tab.title = item.title.orEmpty()
                        ui.pageChanged(tab)
                    }
                }
                ui.offerDownload(url, disposition, mime, agent, length)
            }
        }
        web.setOnLongClickListener {
            val hit = web.hitTestResult
            val link = hit.extra
            if (link == null || Addresses.host(link) == null ||
                hit.type !in setOf(WebView.HitTestResult.SRC_ANCHOR_TYPE, WebView.HitTestResult.IMAGE_TYPE)) {
                false
            } else {
                ui.linkPanel(link, web.settings.userAgentString)
                true
            }
        }
        return web
    }

    fun trim(limit: Int) {
        while (live.size > limit) {
            val victim = live.keys.firstOrNull { !ui.isActiveId(it) } ?: break
            discard(victim, true)
        }
    }
    fun discard(id: String, remember: Boolean) {
        releasePopup(id)
        val web = live.remove(id) ?: return
        if (remember) {
            val state = Bundle()
            if (web.saveState(state) != null) {
                val parcel = Parcel.obtain()
                try {
                    parcel.writeBundle(state)
                    if (parcel.dataSize() <= 512 * 1024) snapshots[id] = state
                } finally { parcel.recycle() }
                while (snapshots.size > 24) snapshots.remove(snapshots.keys.first())
            }
        } else snapshots.remove(id)
        destroy(web)
    }
    fun retain(ids: Set<String>) { snapshots.keys.retainAll(ids) }
    private fun releasePopup(id: String) { pending.remove(id)?.let(::destroy) }
    private fun destroy(web: WebView) {
        (web.parent as? ViewGroup)?.removeView(web)
        web.stopLoading()
        web.webChromeClient = null
        web.webViewClient = WebViewClient()
        web.setDownloadListener(null)
        web.setOnLongClickListener(null)
        web.destroy()
    }
    fun release() {
        handler.removeCallbacksAndMessages(null)
        live.keys.toList().forEach { discard(it, false) }
        snapshots.clear()
    }
}

/** Decompress once per process, independently of page loads. */
private object FilterBundle {
    private val loader = java.util.concurrent.Executors.newSingleThreadExecutor()
    @Volatile private var future: java.util.concurrent.Future<DomainRules>? = null
    @Synchronized fun get(context: android.content.Context): java.util.concurrent.Future<DomainRules> {
        val assets = context.applicationContext.assets
        return future ?: loader.submit<DomainRules> {
            GZIPInputStream(assets.open("hagezi-light.rules")).bufferedReader().useLines(DomainRules::read)
        }.also { future = it; loader.shutdown() }
    }
}
