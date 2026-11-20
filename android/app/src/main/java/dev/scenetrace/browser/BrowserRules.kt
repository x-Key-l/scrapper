package dev.scenetrace.browser

import java.net.URI
import java.net.URLEncoder
import java.util.Locale

object Addresses {
    fun host(value: String): String? = runCatching {
        URI(value).takeIf { it.scheme?.lowercase(Locale.ROOT) in setOf("http", "https") && it.rawUserInfo == null }
            ?.host?.trimEnd('.')?.lowercase(Locale.ROOT)
    }.getOrNull()

    fun resolve(input: String, engine: String): String? {
        val text = input.trim()
        if (text.isEmpty()) return null
        val scheme = Regex("^[A-Za-z][A-Za-z0-9+.-]*:")
        val explicit = text.startsWith("http://", true) || text.startsWith("https://", true)
        val candidate = if (explicit) text else "https://$text"
        val domain = host(candidate)
        if (domain != null && (explicit || '.' in domain || domain == "localhost" || domain.startsWith("["))) return candidate
        if (explicit || scheme.containsMatchIn(text)) return null
        val base = if (engine == "Google") "https://www.google.com/search?q=" else "https://duckduckgo.com/?q="
        return base + URLEncoder.encode(text, "UTF-8")
    }
}

class DomainRules(private val domains: Set<String>) {
    fun matches(domain: String): Boolean {
        var host = domain.lowercase(Locale.ROOT).trimEnd('.')
        while (host.contains('.')) {
            if (host in domains) return true
            host = host.substringAfter('.')
        }
        return false
    }

    companion object {
        fun read(lines: Sequence<String>) = DomainRules(lines.filter { it.startsWith("||") && it.endsWith("^") }
            .map { it.substring(2, it.length - 1) }.toHashSet())
    }
}

object FileNames {
    fun clean(value: String): String {
        val name = value.replace(Regex("""[\p{Cntrl}\p{Cf}\\/:*?"<>|]"""), "_").trim(' ', '.')
        return name.take(88).ifBlank { "download" }
    }

    fun available(value: String, taken: (String) -> Boolean): String {
        val first = clean(value)
        val dot = first.lastIndexOf('.').takeIf { it > 0 } ?: first.length
        var candidate = first
        var index = 1
        while (taken(candidate)) {
            candidate = first.take(dot) + " (${index++})" + first.drop(dot)
        }
        return candidate
    }
}
