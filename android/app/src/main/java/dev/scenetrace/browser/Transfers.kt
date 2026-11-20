package dev.scenetrace.browser

import android.app.DownloadManager
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.webkit.URLUtil
import java.io.File

enum class Stage { QUEUED, RUNNING, WAITING, SAVED, FAILED, CANCELLED, MISSING }
data class Transfer(val id: Long, val name: String, val stage: Stage, val bytes: Long = 0,
                    val total: Long = -1, val detail: String = "")

class Transfers(context: Context, private val store: BrowserStore) {
    private val system = context.getSystemService(DownloadManager::class.java)
    private val directory = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "SceneTrace")

    fun suggested(url: String, disposition: String?, mime: String?) =
        FileNames.clean(URLUtil.guessFileName(url, disposition, mime))

    @Synchronized fun start(url: String, suggested: String, mime: String?, agent: String?): Long {
        require(Addresses.host(url) != null) { "Only direct HTTP and HTTPS links are supported." }
        val name = FileNames.available(suggested) { candidate ->
            File(directory, candidate).exists() || store.readableDatabase.rawQuery(
                "SELECT 1 FROM transfers WHERE name=?", arrayOf(candidate)).use { it.moveToFirst() }
        }
        val request = DownloadManager.Request(Uri.parse(url)).setTitle(name)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "SceneTrace/$name")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
        if (!mime.isNullOrBlank()) request.setMimeType(mime)
        if (!agent.isNullOrBlank()) request.addRequestHeader("User-Agent", agent)
        val id = system.enqueue(request)
        try {
            store.writableDatabase.insertOrThrow("transfers", null, ContentValues().apply { put("id", id); put("name", name) })
        } catch (e: Exception) { system.remove(id); throw e }
        return id
    }

    private fun rows() = store.readableDatabase.rawQuery("SELECT id,name,cancelled FROM transfers ORDER BY id DESC", null).use {
        buildList { while (it.moveToNext()) add(Transfer(it.getLong(0), it.getString(1),
            if (it.getInt(2) == 1) Stage.CANCELLED else Stage.MISSING)) }
    }

    fun list(): List<Transfer> {
        val records = rows()
        val live = mutableMapOf<Long, Transfer>()
        system.query(DownloadManager.Query())?.use { c ->
            fun number(key: String) = c.getLong(c.getColumnIndexOrThrow(key))
            while (c.moveToNext()) {
                val id = number(DownloadManager.COLUMN_ID)
                val bytes = number(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR)
                val total = number(DownloadManager.COLUMN_TOTAL_SIZE_BYTES)
                val status = number(DownloadManager.COLUMN_STATUS).toInt()
                val state = when (status) {
                    DownloadManager.STATUS_PENDING -> Stage.QUEUED
                    DownloadManager.STATUS_RUNNING -> Stage.RUNNING
                    DownloadManager.STATUS_PAUSED -> Stage.WAITING
                    DownloadManager.STATUS_SUCCESSFUL -> {
                        val size = runCatching { system.openDownloadedFile(id).use { it.statSize } }.getOrNull()
                        if (size != null && size >= 0 && size == bytes && (total < 0 || total == size)) Stage.SAVED else Stage.MISSING
                    }
                    else -> Stage.FAILED
                }
                val name = c.getString(c.getColumnIndexOrThrow(DownloadManager.COLUMN_TITLE)).orEmpty()
                live[id] = Transfer(id, name, state, bytes, total, if (state == Stage.FAILED || state == Stage.WAITING)
                    "System code " + number(DownloadManager.COLUMN_REASON) else "")
            }
        }
        return records.map { r -> if (r.stage == Stage.CANCELLED) r else live[r.id]?.copy(name = r.name) ?: r } +
            live.values.filter { t -> records.none { it.id == t.id } }
    }

    @Synchronized fun cancel(id: Long) {
        val record = list().firstOrNull { it.id == id } ?: return
        if (record.stage !in setOf(Stage.QUEUED, Stage.RUNNING, Stage.WAITING)) return
        system.remove(id)
        store.writableDatabase.insertWithOnConflict("transfers", null, ContentValues().apply {
            put("id", id); put("name", record.name); put("cancelled", 1)
        }, android.database.sqlite.SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun uri(id: Long): Uri? = system.getUriForDownloadedFile(id)
    fun type(id: Long): String = system.getMimeTypeForDownloadedFile(id) ?: "application/octet-stream"
}
