package dev.scenetrace.browser

import android.app.DownloadManager
import android.content.Context
import android.os.SystemClock
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.*
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceTest {
    private val ctx = ApplicationProvider.getApplicationContext<Context>()
    private lateinit var fixture: Fixture
    private lateinit var store: BrowserStore
    private lateinit var transfers: Transfers
    @Before fun setup() {
        ctx.getSharedPreferences("browser", Context.MODE_PRIVATE).edit().clear().commit()
        store = BrowserStore(ctx)
        store.writableDatabase.delete("bookmarks", null, null)
        store.clearHistory()
        fixture = Fixture()
        transfers = Transfers(ctx, store)
    }
    @After fun cleanup() {
        val manager = ctx.getSystemService(DownloadManager::class.java)
        val ids = transfers.list().map { it.id }.toLongArray()
        if (ids.isNotEmpty()) manager.remove(*ids)
        store.writableDatabase.delete("transfers", null, null)
        store.close()
        fixture.close()
    }
    private fun waitFor(label: String, condition: () -> Boolean) {
        val end = SystemClock.elapsedRealtime() + 30000
        do {
            if (condition()) return
            SystemClock.sleep(150)
        } while (SystemClock.elapsedRealtime() < end)
        fail("Timed out waiting for $label")
    }
    private fun typeUrl(url: String) {
        onView(withContentDescription("Address or search")).perform(click(), replaceText(url), pressImeActionButton())
    }
    private fun findWeb(v: View): WebView? {
        if (v is WebView) return v
        if (v is ViewGroup) for (i in 0 until v.childCount) findWeb(v.getChildAt(i))?.let { return it }
        return null
    }
    private fun js(activity: BrowserActivity, expression: String) {
        requireNotNull(findWeb(activity.window.decorView)).evaluateJavascript(expression, null)
    }
    private fun page(path: String) = waitFor(path) {
        val current = store.session().current
        current.url == fixture.base + path && current.title == path.removePrefix("/").replaceFirstChar { it.uppercase() }
    }
    private fun clickLabel(label: String) { onView(withText(label)).perform(click()) }
    private fun clickIcon(label: String) { onView(withContentDescription(label)).perform(click()) }

    @Test fun browseSwitchRestoreAndReopen() {
        ActivityScenario.launch(BrowserActivity::class.java).use { scenario ->
            typeUrl(fixture.base + "/one"); page("/one")
            scenario.onActivity { js(it, "location.href='/two'") }; page("/two")
            clickIcon("Browser menu"); clickLabel("Bookmark this page")
            clickIcon("Tabs, 1 open"); clickLabel("New tab")
            typeUrl(fixture.base + "/three"); page("/three")
            clickIcon("Tabs, 2 open"); clickLabel("Two")
            clickIcon("Back"); page("/one")
            clickIcon("Forward"); page("/two")
            clickIcon("Tabs, 2 open"); clickIcon("Close Two"); clickIcon("Close panel")
            page("/three")
            clickIcon("Tabs, 1 open"); clickLabel("Restore closed tab"); page("/two")
            clickIcon("Back"); page("/one")
            clickIcon("Website protection"); clickLabel("Allowlist this website"); clickIcon("Close panel")
            clickIcon("Browser menu"); clickLabel("Settings"); clickLabel("Search engine"); clickLabel("Google")
            clickIcon("Close panel")
            scenario.recreate()
            page("/one")
            assertTrue(store.allowed("127.0.0.1"))
            assertEquals("Google", store.engine)
            assertEquals(2, store.session().tabs.size)
            assertTrue(store.bookmarked(fixture.base + "/two"))
            assertTrue(store.pages(false).any { it.url.endsWith("/three") })
        }
    }

    @Test fun settingsHistoryAndBookmarksSurviveReopen() {
        store.engine = "Google"
        store.protection = false
        store.allow("example.org", true)
        val page = Page("https://example.org/file", "Example")
        store.savePage(page); store.savePage(page, true)
        BrowserStore(ctx).use { other ->
            assertEquals(listOf(page), other.pages(true))
            assertEquals(listOf(page), other.pages(false))
            assertFalse(other.protection); assertTrue(other.allowed("example.org"))
            assertFalse(other.allowed("other.example.org")); assertEquals("Google", other.engine)
            other.removeBookmark(page.url)
            assertTrue(other.pages(true).isEmpty()); assertEquals(listOf(page), other.pages(false))
        }
    }

    @Test fun browserDownloadMatchesFixtureAfterTabClose() {
        ActivityScenario.launch(BrowserActivity::class.java).use { scenario ->
            typeUrl(fixture.base + "/one"); page("/one")
            scenario.onActivity { js(it, "location.href='/file'") }
            onView(withText("Download file?")).check(androidx.test.espresso.assertion.ViewAssertions.matches(isDisplayed()))
            clickLabel("Download")
            clickIcon("Tabs, 1 open"); clickIcon("Close One"); clickIcon("Close panel")
            waitFor("completed file") { transfers.list().any { it.stage == Stage.SAVED } }
            val record = transfers.list().first { it.stage == Stage.SAVED }
            val bytes = ctx.contentResolver.openInputStream(transfers.uri(record.id)!!)!!.use { it.readBytes() }
            assertArrayEquals(fixture.file, bytes)
            assertEquals(fixture.file.size.toLong(), record.bytes)
            BrowserStore(ctx).use { reopened -> assertEquals(record, Transfers(ctx, reopened).list().first()) }
        }
    }

    @Test fun downloadRedirectDuplicatesFailureAndCancellation() {
        val one = transfers.start(fixture.base + "/redirect", "same.bin", null, null)
        val two = transfers.start(fixture.base + "/slow", "same.bin", null, null)
        val bad = transfers.start(fixture.base + "/missing", "missing.bin", null, null)
        waitFor("slow transfer running") { transfers.list().any { it.id == two && it.stage == Stage.RUNNING } }
        transfers.cancel(two)
        waitFor("real completion and HTTP failure") {
            val rows = transfers.list().associateBy { it.id }
            rows[one]?.stage == Stage.SAVED && rows[bad]?.stage == Stage.FAILED
        }
        val rows = transfers.list().associateBy { it.id }
        assertNotEquals(rows[one]!!.name, rows[two]!!.name)
        assertEquals(Stage.CANCELLED, rows[two]!!.stage)
        ctx.getSystemService(DownloadManager::class.java).remove(one)
        assertEquals(Stage.MISSING, transfers.list().first { it.id == one }.stage)
    }
}
