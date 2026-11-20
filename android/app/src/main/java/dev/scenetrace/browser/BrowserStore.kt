package dev.scenetrace.browser

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class Page(val url: String, val title: String)
data class Tab(val id: String = UUID.randomUUID().toString(), var url: String = "", var title: String = "")
data class Session(val tabs: MutableList<Tab>, var active: String, val closed: MutableList<Tab>) {
    val current get() = tabs.first { it.id == active }
    fun add(tab: Tab = Tab()) { tabs.add(tab); active = tab.id }
    fun close(id: String) {
        val index = tabs.indexOfFirst { it.id == id }
        if (index < 0) return
        closed.add(0, tabs.removeAt(index))
        if (closed.size > 12) closed.removeAt(closed.lastIndex)
        if (tabs.isEmpty()) add() else if (active == id) active = tabs[index.coerceAtMost(tabs.lastIndex)].id
    }
    fun restore() { if (closed.isNotEmpty()) add(closed.removeAt(0)) }
}

class BrowserStore(context: Context) : SQLiteOpenHelper(context, "browser.db", null, 1) {
    companion object {
        @Volatile private var instance: BrowserStore? = null
        fun shared(context: Context): BrowserStore = instance ?: synchronized(this) {
            instance ?: BrowserStore(context.applicationContext).also { instance = it }
        }
    }
    private val prefs = context.getSharedPreferences("browser", Context.MODE_PRIVATE)
    var protection: Boolean
        get() = prefs.getBoolean("protect", true)
        set(value) { prefs.edit().putBoolean("protect", value).apply() }
    var engine: String
        get() = prefs.getString("engine", "DuckDuckGo") ?: "DuckDuckGo"
        set(value) { prefs.edit().putString("engine", value).apply() }
    fun allowed(host: String) = host in prefs.getStringSet("allowed", emptySet()).orEmpty()
    fun allow(host: String, enabled: Boolean) {
        val hosts = prefs.getStringSet("allowed", emptySet()).orEmpty().toMutableSet()
        if (enabled) hosts.add(host) else hosts.remove(host)
        prefs.edit().putStringSet("allowed", hosts).apply()
    }

    override fun onCreate(db: SQLiteDatabase) {
        for (table in listOf("history", "bookmarks")) {
            db.execSQL("CREATE TABLE $table (url TEXT PRIMARY KEY, title TEXT NOT NULL, time INTEGER NOT NULL)")
        }
        db.execSQL("CREATE TABLE transfers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun savePage(page: Page, bookmark: Boolean = false) {
        if (Addresses.host(page.url) == null) return
        val values = ContentValues().apply {
            put("url", page.url); put("title", page.title.take(400)); put("time", System.currentTimeMillis())
        }
        writableDatabase.insertWithOnConflict(if (bookmark) "bookmarks" else "history", null, values, SQLiteDatabase.CONFLICT_REPLACE)
        if (!bookmark) writableDatabase.execSQL("DELETE FROM history WHERE rowid IN (SELECT rowid FROM history ORDER BY time DESC, rowid DESC LIMIT -1 OFFSET 500)")
    }
    fun pages(bookmarks: Boolean, limit: Int = 500): List<Page> {
        val table = if (bookmarks) "bookmarks" else "history"
        return readableDatabase.rawQuery("SELECT url,title FROM $table ORDER BY time DESC, rowid DESC LIMIT ?", arrayOf(limit.toString())).use {
            buildList { while (it.moveToNext()) add(Page(it.getString(0), it.getString(1))) }
        }
    }
    fun bookmarked(url: String) = readableDatabase.rawQuery("SELECT 1 FROM bookmarks WHERE url=?", arrayOf(url)).use { it.moveToFirst() }
    fun removeBookmark(url: String) { writableDatabase.delete("bookmarks", "url=?", arrayOf(url)) }
    fun clearHistory() { writableDatabase.delete("history", null, null) }

    fun save(session: Session) {
        fun encode(tabs: List<Tab>) = JSONArray().apply {
            tabs.forEach { put(JSONArray(listOf(it.id, it.url, it.title.take(400)))) }
        }
        val json = JSONObject().put("tabs", encode(session.tabs)).put("active", session.active).put("closed", encode(session.closed))
        prefs.edit().putString("session", json.toString()).apply()
    }
    fun session(): Session {
        val json = runCatching { JSONObject(prefs.getString("session", "{}")!!) }.getOrDefault(JSONObject())
        fun tabs(key: String): MutableList<Tab> {
            val items = json.optJSONArray(key) ?: JSONArray()
            return (0 until items.length()).mapNotNull { i -> items.optJSONArray(i)?.let {
                Tab(it.optString(0), it.optString(1), it.optString(2))
            } }.toMutableList()
        }
        val open = tabs("tabs").ifEmpty { mutableListOf(Tab()) }
        return Session(open, json.optString("active").takeIf { id -> open.any { it.id == id } } ?: open.first().id, tabs("closed"))
    }
}
