package dev.scenetrace.browser

import java.io.Closeable
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors
import kotlin.concurrent.thread

/** Local HTTP fixture reachable by both WebView and Android's Downloads provider. */
class Fixture : Closeable {
    private val socket = ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))
    private val workers = Executors.newCachedThreadPool()
    val requests = java.util.concurrent.ConcurrentLinkedQueue<String>()
    val base = "http://127.0.0.1:${socket.localPort}"
    val file = ByteArray(48137) { (it % 251).toByte() }
    init {
        thread(isDaemon = true, name = "fixture-http") {
            while (!socket.isClosed) {
                val client = runCatching { socket.accept() }.getOrNull() ?: break
                workers.submit { runCatching { client.use(::respond) } }
            }
        }
    }
    private fun respond(client: Socket) {
        client.soTimeout = 5000
        val reader = client.getInputStream().bufferedReader()
        val path = reader.readLine()?.split(' ')?.getOrNull(1) ?: return
        requests.add(path)
        while (!reader.readLine().isNullOrEmpty()) { /* consume request headers */ }
        val out = client.getOutputStream()
        val binary = path in listOf("/file", "/slow")
        val redirect = path == "/redirect" || path == "/ad-redirect"
        val status = when {
            redirect -> "302 Found"
            path == "/missing" -> "404 Not Found"
            else -> "200 OK"
        }
        val title = path.removePrefix("/").replaceFirstChar { it.uppercase() }
        val body = when (path) {
            "/popup-link" -> "<a style='position:fixed;inset:0' target='_blank' href='/child'>Open child tab</a>"
            "/ad-link" -> "<a style='position:fixed;inset:0' target='_blank' href='https://doubleclick.net/ad'>Advert</a>"
            else -> "<a href='/two'>Next page</a><a href='/file'>Download</a>"
        }
        val page = "<html><head><title>$title</title></head><body>$body</body></html>"
        val payload = if (binary) file else page.toByteArray()
        val repeat = if (path == "/slow") 400 else 1
        val headers = buildString {
            append("HTTP/1.1 $status\r\nConnection: close\r\n")
            if (redirect) append("Location: " + (if (path == "/redirect") "/file" else "https://doubleclick.net/ad") + "\r\n")
            append("Content-Length: ${payload.size * repeat}\r\n")
            if (binary) append("Content-Type: application/octet-stream\r\nContent-Disposition: attachment; filename=fixture.bin\r\n")
            else append("Content-Type: text/html; charset=utf-8\r\n")
            append("\r\n")
        }
        out.write(headers.toByteArray())
        repeat(repeat) { out.write(payload); out.flush(); if (repeat > 1) Thread.sleep(100) }
    }
    override fun close() { socket.close(); workers.shutdownNow() }
}
