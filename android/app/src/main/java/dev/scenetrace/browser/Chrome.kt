package dev.scenetrace.browser

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.widget.*

internal val ink = Color.rgb(17, 23, 21)
internal val surface = Color.rgb(30, 39, 35)
internal val mint = Color.rgb(128, 233, 207)
internal val bright = Color.rgb(235, 244, 239)
internal val muted = Color.rgb(171, 188, 179)
internal const val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
internal const val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
internal fun Context.dp(n: Int) = (resources.displayMetrics.density * n + .5f).toInt()
internal fun Context.shape(color: Int, radius: Int) = GradientDrawable().apply {
    setColor(color); cornerRadius = dp(radius).toFloat()
}
internal fun Context.touch(color: Int = Color.TRANSPARENT, radius: Int = 12) =
    RippleDrawable(ColorStateList.valueOf(0x397fe8ce), shape(color, radius), null)
internal fun Context.text(value: String, size: Int, color: Int = bright, bold: Boolean = false) = TextView(this).apply {
    text = value; textSize = size.toFloat(); setTextColor(color)
    if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
}
internal fun Context.icon(resource: Int, label: String, action: () -> Unit) = ImageButton(this).apply {
    setImageResource(resource); contentDescription = label; tooltipText = label
    scaleType = ImageView.ScaleType.CENTER; background = touch()
    setOnClickListener { action() }
}
internal fun Context.row() = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
internal fun Context.column() = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
internal fun View.pad(x: Int, y: Int) { setPadding(context.dp(x), context.dp(y), context.dp(x), context.dp(y)) }
internal fun TextView.single() { maxLines = 1; ellipsize = TextUtils.TruncateAt.END }
internal fun Context.entry(symbol: Int, title: String, sub: String = "", action: () -> Unit): LinearLayout {
    val line = row().apply {
        minimumHeight = dp(56); background = touch(); pad(12, 6); isFocusable = true
        setOnClickListener { action() }
    }
    line.addView(ImageView(this).apply { setImageResource(symbol); setColorFilter(mint) }, dp(24), dp(24))
    val labels = column().apply { pad(14, 3) }
    labels.addView(text(title, 16).apply { single() })
    if (sub.isNotBlank()) labels.addView(text(sub, 13, muted).apply { single() })
    line.addView(labels, LinearLayout.LayoutParams(0, WRAP, 1f))
    return line
}

internal class Sheet(val owner: Activity, title: String) {
    val dialog = Dialog(owner)
    val entries = owner.column()
    private val wrap = owner.column()
    private val scroll = ScrollView(owner)
    init {
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        wrap.apply { background = owner.shape(surface, 20); pad(12, 10) }
        val heading = owner.row()
        heading.addView(owner.text(title, 23, bright, true).apply { pad(12, 8) }, LinearLayout.LayoutParams(0, WRAP, 1f))
        heading.addView(owner.icon(R.drawable.ic_stop, "Close panel") { dialog.dismiss() }, owner.dp(48), owner.dp(48))
        wrap.addView(heading)
        wrap.addView(scroll.apply { addView(entries); isFillViewport = false }, MATCH, WRAP)
        dialog.setContentView(wrap)
    }
    fun list(size: Int, rowAt: (Int) -> View) {
        if (scroll.parent === wrap) {
            wrap.removeView(scroll)
            scroll.removeView(entries)
            wrap.addView(entries)
        }
        val list = ListView(owner).apply {
            divider = null
            adapter = object : BaseAdapter() {
                override fun getCount() = size
                override fun getItem(position: Int) = position
                override fun getItemId(position: Int) = position.toLong()
                override fun getView(position: Int, convertView: View?, parent: ViewGroup) = rowAt(position)
            }
        }
        wrap.addView(list, MATCH, WRAP)
    }
    fun show() {
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT)); setGravity(Gravity.BOTTOM)
            setLayout(minOf(owner.resources.displayMetrics.widthPixels, owner.dp(600)), WRAP)
            navigationBarColor = surface
        }
        dialog.show()
    }
    fun item(icon: Int, title: String, sub: String = "", action: () -> Unit) =
        owner.entry(icon, title, sub) { dialog.dismiss(); action() }.also { entries.addView(it) }
    fun message(value: String) { entries.addView(owner.text(value, 15, muted).apply { pad(12, 20) }) }
}
