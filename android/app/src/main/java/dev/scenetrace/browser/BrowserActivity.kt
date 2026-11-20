package dev.scenetrace.browser

import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.ComponentCallbacks2
import android.content.Intent
import android.content.res.ColorStateList
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.text.format.Formatter
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.WebView
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.*

class BrowserActivity : ComponentActivity() {
    private lateinit var store: BrowserStore
    private lateinit var transfers: Transfers
    private lateinit var session: Session
    private lateinit var views: BrowserViews
    private lateinit var frame: FrameLayout
    private lateinit var address: EditText
    private lateinit var progress: ProgressBar
    private lateinit var reload: ImageButton
    private lateinit var shield: ImageButton
    private lateinit var back: ImageButton
    private lateinit var forward: ImageButton
    private lateinit var count: TextView
    private var web: WebView? = null
    private var shown: Sheet? = null
    private var loading = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = BrowserStore.shared(this)
        transfers = Transfers(applicationContext, store)
        session = store.session()
        views = BrowserViews(this, store)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val root = column().apply { setBackgroundColor(ink); isFocusableInTouchMode = true }
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val area = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime())
            v.setPadding(area.left, area.top, area.right, area.bottom)
            insets
        }
        val top = row().apply { pad(6, 4) }
        shield = icon(R.drawable.ic_shield, "Website protection", ::protectionPanel)
        top.addView(shield, dp(48), dp(48))
        address = EditText(this).apply {
            setSingleLine(); inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            imeOptions = EditorInfo.IME_ACTION_GO or EditorInfo.IME_FLAG_NO_EXTRACT_UI
            textSize = 16f; setTextColor(bright); setHintTextColor(muted)
            hint = "Search or enter address"; contentDescription = "Address or search"
            background = shape(surface, 14); pad(14, 0); setSelectAllOnFocus(true)
            setOnEditorActionListener { _, action, event ->
                if (action == EditorInfo.IME_ACTION_GO || (event?.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)) {
                    val url = Addresses.resolve(text.toString(), store.engine)
                    if (url == null) notice("Enter a website address or search terms") else navigate(url)
                    true
                } else false
            }
            onFocusChangeListener = View.OnFocusChangeListener { _, focused ->
                if (!focused && ::session.isInitialized) setText(session.current.url)
            }
        }
        top.addView(address, LinearLayout.LayoutParams(0, dp(48), 1f))
        reload = icon(R.drawable.ic_reload, "Refresh") {
            if (loading) { web?.stopLoading(); showProgress(100) } else web?.reload()
        }
        top.addView(reload, dp(48), dp(48)); root.addView(top)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100; progressTintList = ColorStateList.valueOf(mint)
        }
        root.addView(progress, MATCH, dp(2))
        frame = FrameLayout(this).apply { isFocusableInTouchMode = true }
        root.addView(frame, LinearLayout.LayoutParams(MATCH, 0, 1f))
        root.addView(View(this).apply { setBackgroundColor(surface) }, MATCH, dp(1))
        val bottom = row().apply { pad(6, 0) }
        fun nav(view: View) = bottom.addView(view, LinearLayout.LayoutParams(0, dp(52), 1f))
        back = icon(R.drawable.ic_back, "Back") { goBack() }; nav(back)
        forward = icon(R.drawable.ic_forward, "Forward") { web?.goForward() }; nav(forward)
        count = text("", 15, mint, true).apply {
            gravity = Gravity.CENTER; background = touch(); setOnClickListener { tabsPanel() }; isFocusable = true
        }
        nav(count)
        nav(icon(R.drawable.ic_download, "Downloads", ::downloadsPanel))
        nav(icon(R.drawable.ic_more, "Browser menu", ::menuPanel))
        root.addView(bottom)
        setContentView(root)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (address.hasFocus()) endEditing()
                else if (!goBack()) finish()
            }
        })
        activate()
    }

    private fun endEditing() {
        getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(address.windowToken, 0)
        frame.requestFocus()
    }
    fun notice(message: String) { Toast.makeText(this, message, Toast.LENGTH_SHORT).show() }
    fun isActive(tab: Tab) = isActiveId(tab.id)
    fun isActiveId(id: String) = session.active == id

    private fun activate() {
        endEditing()
        web?.onPause()
        web = null
        frame.removeAllViews()
        val tab = session.current
        if (tab.url.isEmpty()) home() else {
            val view = views.obtain(tab)
            frame.addView(view, MATCH, MATCH); web = view
            view.onResume()
        }
        address.setText(tab.url)
        showProgress(web?.progress ?: 100)
        updateChrome()
        store.save(session)
    }
    private fun updateChrome() {
        val host = Addresses.host(session.current.url).orEmpty()
        shield.setColorFilter(if (store.protection && !store.allowed(host)) mint else muted)
        back.isEnabled = web != null || session.tabs.size > 1
        forward.isEnabled = web?.canGoForward() == true
        for (button in listOf(back, forward)) button.alpha = if (button.isEnabled) 1f else .35f
        count.text = resources.getQuantityString(R.plurals.tab_count, session.tabs.size, session.tabs.size)
        count.contentDescription = "Tabs, ${session.tabs.size} open"
        reload.isEnabled = web != null
        reload.alpha = if (reload.isEnabled) 1f else .35f
    }
    fun pageChanged(tab: Tab) {
        store.save(session)
        if (isActive(tab)) {
            if (!address.hasFocus()) address.setText(tab.url)
            updateChrome()
        }
    }
    fun showProgress(percent: Int) {
        loading = percent < 100
        progress.progress = percent
        progress.visibility = if (loading) View.VISIBLE else View.INVISIBLE
        reload.setImageResource(if (loading) R.drawable.ic_stop else R.drawable.ic_reload)
        reload.contentDescription = if (loading) "Stop loading" else "Refresh"
        reload.tooltipText = reload.contentDescription
    }
    fun rendererLost(tab: Tab) {
        if (!isActive(tab)) return
        web = null
        frame.removeAllViews()
        showProgress(100)
        frame.addView(entry(R.drawable.ic_reload, "Page closed by Android", "Tap to reload this tab") { activate() },
            FrameLayout.LayoutParams(MATCH, WRAP, Gravity.CENTER))
    }
    private fun navigate(url: String) {
        if (Addresses.host(url) == null) { notice("This address is unsupported"); return }
        endEditing()
        if (web == null) {
            session.current.url = url
            activate()
        } else web?.loadUrl(url)
    }
    fun newTab(url: String = "") { session.add(Tab(url = url)); activate() }
    private fun select(id: String) { session.active = id; activate() }
    private fun close(id: String) {
        if (isActiveId(id)) { web?.onPause(); web = null }
        views.discard(id, true)
        session.close(id)
        views.retain((session.tabs + session.closed).map { it.id }.toSet())
        if (web == null) activate() else { updateChrome(); store.save(session) }
    }
    private fun goBack(): Boolean {
        when {
            web?.canGoBack() == true -> web?.goBack()
            session.tabs.size > 1 -> close(session.active)
            session.current.url.isNotEmpty() -> {
                web = null; views.discard(session.active, false)
                session.current.apply { url = ""; title = "" }; activate()
            }
            else -> return false
        }
        return true
    }

    private fun home() {
        val page = column().apply { pad(22, 24) }
        val brand = row()
        brand.addView(ImageView(this).apply { setImageResource(R.drawable.brand) }, dp(46), dp(46))
        brand.addView(text("SceneTrace", 32, bright, true).apply { pad(12, 0); letterSpacing = -.04f })
        page.addView(brand)
        val search = entry(R.drawable.ic_search, "Search the web", store.engine) {
            address.requestFocus()
            getSystemService(InputMethodManager::class.java).showSoftInput(address, InputMethodManager.SHOW_IMPLICIT)
        }.apply { background = touch(surface, 14); minimumHeight = dp(70) }
        page.addView(search, LinearLayout.LayoutParams(MATCH, WRAP).apply { topMargin = dp(22); bottomMargin = dp(14) })
        page.addView(entry(R.drawable.ic_book, "Bookmarks") { pagesPanel(true) })
        page.addView(entry(R.drawable.ic_history, "History") { pagesPanel(false) })
        val recent = store.pages(false, 5)
        if (recent.isNotEmpty()) {
            page.addView(text("Recently visited", 18, mint, true).apply { pad(12, 14) })
            recent.forEach { p -> page.addView(entry(R.drawable.ic_globe, pageTitle(p), Addresses.host(p.url).orEmpty()) { navigate(p.url) }) }
        }
        frame.addView(ScrollView(this).apply { addView(page) })
    }

    private fun pageTitle(page: Page) = page.title.ifBlank { Addresses.host(page.url) ?: "New tab" }
    private fun panel(title: String, fill: Sheet.() -> Unit): Sheet {
        shown?.dialog?.dismiss()
        val sheet = Sheet(this, title)
        shown = sheet
        sheet.fill()
        sheet.dialog.setOnDismissListener { if (shown === sheet) shown = null }
        sheet.show()
        return sheet
    }
    private fun tabsPanel() { panel("Tabs") {
        item(R.drawable.ic_plus, "New tab") { newTab() }
        if (session.closed.isNotEmpty()) item(R.drawable.ic_restore, "Restore closed tab",
            pageTitle(Page(session.closed.first().url, session.closed.first().title))) { session.restore(); activate() }
        session.tabs.forEach { tab ->
            val title = pageTitle(Page(tab.url, tab.title))
            val line = item(if (isActive(tab)) R.drawable.ic_check else R.drawable.ic_tabs, title, Addresses.host(tab.url).orEmpty()) { select(tab.id) }
            line.addView(icon(R.drawable.ic_stop, "Close $title") {
                dialog.dismiss(); close(tab.id); tabsPanel()
            }, dp(48), dp(48))
        }
    } }
    private fun menuPanel() { panel("Browser") {
        item(R.drawable.ic_plus, "New tab") { newTab() }
        if (session.current.url.isNotBlank()) {
            val page = Page(session.current.url, session.current.title)
            val saved = store.bookmarked(page.url)
            item(R.drawable.ic_book, if (saved) "Remove bookmark" else "Bookmark this page") {
                if (saved) store.removeBookmark(page.url) else store.savePage(page, true)
                notice(if (saved) "Bookmark removed" else "Bookmark saved")
            }
            item(R.drawable.ic_external, "Open in external browser") { launch(Intent(Intent.ACTION_VIEW, Uri.parse(page.url))) }
        }
        item(R.drawable.ic_book, "Bookmarks") { pagesPanel(true) }
        item(R.drawable.ic_history, "History") { pagesPanel(false) }
        item(R.drawable.ic_settings, "Settings") { settingsPanel() }
    } }
    private fun pagesPanel(bookmarks: Boolean) { panel(if (bookmarks) "Bookmarks" else "History") {
        val pages = store.pages(bookmarks, if (bookmarks) -1 else 500)
        if (pages.isEmpty()) message(if (bookmarks) "Save a page from the browser menu." else "Visited pages appear here.")
        if (!bookmarks && pages.isNotEmpty()) item(R.drawable.ic_history, "Clear history") {
            AlertDialog.Builder(this@BrowserActivity).setMessage("Clear your browsing history?")
                .setNegativeButton("Keep", null).setPositiveButton("Clear") { _, _ ->
                    store.clearHistory(); if (web == null) activate(); pagesPanel(false)
                }.show()
        }
        if (pages.isNotEmpty()) list(pages.size) { index ->
            val p = pages[index]
            val line = entry(R.drawable.ic_globe, pageTitle(p), p.url) { dialog.dismiss(); navigate(p.url) }
            if (bookmarks) line.addView(icon(R.drawable.ic_stop, "Remove bookmark") {
                dialog.dismiss(); store.removeBookmark(p.url); pagesPanel(true)
            }, dp(48), dp(48))
            line
        }
    } }
    private fun settingsPanel() { panel("Settings") {
        item(R.drawable.ic_search, "Search engine", store.engine) {
            val options = arrayOf("DuckDuckGo", "Google")
            AlertDialog.Builder(this@BrowserActivity).setTitle("Search engine")
                .setSingleChoiceItems(options, options.indexOf(store.engine)) { d, index ->
                    store.engine = options[index]; d.dismiss(); if (web == null) activate(); settingsPanel()
                }.show()
        }
        item(R.drawable.ic_shield, "Website protection", if (store.protection) "On" else "Off") { protectionPanel() }
    } }
    private fun protectionPanel() { panel("Website protection") {
        item(R.drawable.ic_shield, "Block known ads and trackers", if (store.protection) "On globally" else "Off globally") {
            store.protection = !store.protection; updateChrome(); web?.reload(); protectionPanel()
        }
        Addresses.host(session.current.url)?.let { host ->
            item(R.drawable.ic_globe, "Allowlist this website", "$host · " + if (store.allowed(host)) "Allowed" else "Off") {
                store.allow(host, !store.allowed(host)); updateChrome(); web?.reload(); protectionPanel()
            }
        }
        message("Uses the bundled HaGeZi Light domain list. Allowlist a site if a player or sign-in link stops working.")
    } }

    fun offerDownload(url: String, disposition: String?, mime: String?, agent: String?, length: Long) {
        if (Addresses.host(url) == null) { notice("This download needs a direct HTTP or HTTPS link"); return }
        val name = transfers.suggested(url, disposition, mime)
        val size = if (length >= 0) " · " + Formatter.formatFileSize(this, length) else ""
        AlertDialog.Builder(this).setTitle("Download file?").setMessage("$name\n\n${Addresses.host(url)}$size\nDownloads/SceneTrace")
            .setNegativeButton("Cancel", null).setPositiveButton("Download") { _, _ ->
                runCatching { transfers.start(url, name, mime, agent) }
                    .onSuccess { notice("Download queued") }.onFailure { notice("Could not start download: ${it.localizedMessage}") }
            }.show()
    }
    private fun downloadsPanel() {
        val sheet = panel("Downloads") { message("Checking transfers…") }
        val monitor = lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.RESUMED) {
                var previous: List<Transfer>? = null
                while (sheet.dialog.isShowing) {
                    val rows = withContext(Dispatchers.IO) { runCatching { transfers.list() }.getOrNull() }
                    if (!sheet.dialog.isShowing) break
                    if (rows == null || rows != previous) {
                        sheet.entries.removeAllViews()
                        previous = rows
                        if (rows == null) sheet.message("Could not read transfers. Check device storage.")
                        else if (rows.isEmpty()) sheet.message("Files you download from websites appear here.")
                        else rows.forEach { downloadRow(sheet, it) }
                    }
                    if (rows?.none { it.stage.active } != false) break
                    delay(1100)
                }
            }
        }
        sheet.dialog.setOnDismissListener { monitor.cancel(); if (shown === sheet) shown = null }
    }
    private fun downloadRow(sheet: Sheet, transfer: Transfer) {
        val state = when (transfer.stage) {
            Stage.QUEUED -> "Queued"
            Stage.RUNNING -> "Downloading"
            Stage.WAITING -> "Waiting"
            Stage.SAVED -> "Saved"
            Stage.FAILED -> "Failed"
            Stage.CANCELLED -> "Cancelled"
            Stage.MISSING -> "File unavailable"
        }
        val bytes = Formatter.formatFileSize(this, transfer.bytes)
        val total = if (transfer.total > 0) " / " + Formatter.formatFileSize(this, transfer.total) else ""
        val detail = listOf(state, bytes + total, transfer.detail).filter { it.isNotEmpty() }.joinToString(" · ")
        val line = entry(R.drawable.ic_download, transfer.name, detail) {
            if (transfer.stage == Stage.SAVED) {
                transfers.uri(transfer.id)?.let { uri ->
                    launch(Intent(Intent.ACTION_VIEW).setDataAndType(uri, transfers.type(transfer.id)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                } ?: notice("File unavailable")
            }
        }
        if (transfer.stage.active) {
            line.addView(icon(R.drawable.ic_stop, "Cancel ${transfer.name}") {
                AlertDialog.Builder(this).setMessage("Cancel ${transfer.name}?").setNegativeButton("Keep", null)
                    .setPositiveButton("Cancel download") { _, _ ->
                        runCatching { transfers.cancel(transfer.id) }.onFailure { notice("Could not cancel transfer") }
                    }.show()
            }, dp(48), dp(48))
        }
        sheet.entries.addView(line)
    }
    private fun launch(intent: Intent) {
        try { startActivity(intent) } catch (_: ActivityNotFoundException) { notice("No installed app can open this item") }
        catch (_: SecurityException) { notice("Android could not open this item") }
    }

    override fun onPause() { web?.onPause(); store.save(session); super.onPause() }
    override fun onResume() { super.onResume(); web?.onResume() }
    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW && ::views.isInitialized) views.trim(1)
    }
    override fun onDestroy() {
        shown?.dialog?.dismiss()
        views.release(); web = null
        // Transfer queries use the application context and may finish during teardown.
        super.onDestroy()
    }
}
