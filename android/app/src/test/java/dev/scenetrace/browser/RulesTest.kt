package dev.scenetrace.browser

import org.junit.Assert.*
import org.junit.Test

class RulesTest {
    @Test fun resolvesNavigationAndSearch() {
        assertEquals("https://example.org/path", Addresses.resolve("example.org/path", "Google"))
        assertEquals("http://localhost:9000/", Addresses.resolve("http://localhost:9000/", "Google"))
        assertEquals("https://duckduckgo.com/?q=a+%26+b", Addresses.resolve("a & b", "DuckDuckGo"))
        assertNull(Addresses.resolve("javascript:alert(1)", "Google"))
        assertNull(Addresses.resolve("file:///sdcard/abc", "Google"))
        assertNull(Addresses.host("https://example.org@attacker.com/"))
    }

    @Test fun matchesOnlyDomainBoundaries() {
        val rules = DomainRules.read(sequenceOf("! metadata", "||ad.example^", "unrecognized"))
        assertTrue(rules.matches("CDN.ad.example."))
        assertFalse(rules.matches("notad.example"))
        assertFalse(rules.matches("ad.example.org"))
    }

    @Test fun fileNamesStayInsideDownloadDirectory() {
        assertEquals("download", FileNames.clean(".."))
        assertFalse(FileNames.clean("../folder/test\\file").contains('/'))
        assertEquals("film (2).mp4", FileNames.available("film.mp4") { it in setOf("film.mp4", "film (1).mp4") })
        assertEquals("LICENSE (1)", FileNames.available("LICENSE") { it == "LICENSE" })
    }

    @Test fun tabsSelectCloseAndRestoreByStableId() {
        val first = Tab(url = "https://one.test")
        val session = Session(mutableListOf(first), first.id, mutableListOf())
        val second = Tab(url = "https://two.test")
        session.add(second)
        session.close(first.id)
        assertEquals(second, session.current)
        session.restore()
        assertEquals(first, session.current)
        session.close(first.id)
        assertEquals(second, session.current)
        session.close(second.id)
        assertEquals(1, session.tabs.size)
        assertEquals("", session.current.url)
    }
}
