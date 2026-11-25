package com.winlator.star.i18n

import android.content.Context
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import org.json.JSONObject
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

object JaOverlay {
    private data class PatternRule(val regex: Regex, val replace: String)
    private data class Dict(
        val exact: Map<String, String>,
        val patterns: List<PatternRule>,
    )

    @Volatile
    private var cachedDict: Dict? = null
    private val cache = ConcurrentHashMap<String, String>()

    private fun isJapanese(context: Context): Boolean {
        val appLocale = context.resources.configuration.locales.let {
            if (it.isEmpty) Locale.getDefault() else it[0]
        }
        return appLocale.language.equals("ja", ignoreCase = true) ||
            Locale.getDefault().language.equals("ja", ignoreCase = true)
    }

    private fun dict(context: Context): Dict {
        cachedDict?.let { return it }
        synchronized(this) {
            cachedDict?.let { return it }
            val loaded = runCatching {
                val raw = context.applicationContext.assets
                    .open("ja_classic_dict.json")
                    .bufferedReader(Charsets.UTF_8)
                    .use { it.readText() }
                val root = JSONObject(raw)
                val exactObj = root.optJSONObject("exact")
                val exactMap = HashMap<String, String>(exactObj?.length() ?: 0)
                if (exactObj != null) {
                    val keys = exactObj.keys()
                    while (keys.hasNext()) {
                        val k = keys.next()
                        exactMap[k] = exactObj.getString(k)
                    }
                }
                val patArr = root.optJSONArray("patterns")
                val patList = ArrayList<PatternRule>(patArr?.length() ?: 0)
                if (patArr != null) {
                    for (i in 0 until patArr.length()) {
                        val item = patArr.getJSONObject(i)
                        val regexStr = item.optString("regex", "")
                        val replStr = item.optString("replace", "")
                        if (regexStr.isNotEmpty()) {
                            runCatching { Regex(regexStr) }.getOrNull()?.let {
                                patList.add(PatternRule(it, replStr))
                            }
                        }
                    }
                }
                Dict(exactMap, patList)
            }.getOrElse { Dict(emptyMap(), emptyList()) }
            cachedDict = loaded
            return loaded
        }
    }

    private fun translateCore(d: Dict, text: String): String {
        d.exact[text]?.let { return it }
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return text
        val lead = text.substring(0, text.indexOf(trimmed))
        val trail = text.substring(text.indexOf(trimmed) + trimmed.length)

        d.exact[trimmed]?.let { return lead + it + trail }

        for (p in d.patterns) {
            val m = p.regex.matchEntire(trimmed)
            if (m != null) {
                var out = p.replace
                for (g in m.groupValues.size - 1 downTo 1) {
                    out = out.replace("$$g", m.groupValues[g])
                }
                return lead + out + trail
            }
        }

        if ('\n' in trimmed) {
            val lines = trimmed.split('\n')
            var changed = false
            val mapped = lines.map { ln ->
                val t = ln.trim()
                val res = d.exact[t]
                if (res != null) {
                    changed = true
                    ln.replace(t, res)
                } else {
                    var sub = ln
                    for (p in d.patterns) {
                        val m = p.regex.matchEntire(t)
                        if (m != null) {
                            var out = p.replace
                            for (g in m.groupValues.size - 1 downTo 1) {
                                out = out.replace("$$g", m.groupValues[g])
                            }
                            changed = true
                            sub = ln.replace(t, out)
                            break
                        }
                    }
                    sub
                }
            }
            if (changed) return lead + mapped.joinToString("\n") + trail
        }

        return text
    }

    fun tr(context: Context, raw: String): String {
        if (raw.isEmpty() || !isJapanese(context)) return raw
        cache[raw]?.let { return it }
        val d = dict(context)
        if (d.exact.isEmpty() && d.patterns.isEmpty()) return raw
        val translated = translateCore(d, raw)
        if (cache.size < 8192) {
            cache[raw] = translated
        }
        return translated
    }

    @Composable
    fun tr(raw: String): String = tr(LocalContext.current, raw)
}

@Composable
fun Text(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    fontSize: TextUnit = TextUnit.Unspecified,
    fontStyle: FontStyle? = null,
    fontWeight: FontWeight? = null,
    fontFamily: FontFamily? = null,
    letterSpacing: TextUnit = TextUnit.Unspecified,
    textDecoration: TextDecoration? = null,
    textAlign: TextAlign? = null,
    lineHeight: TextUnit = TextUnit.Unspecified,
    overflow: TextOverflow = TextOverflow.Clip,
    softWrap: Boolean = true,
    maxLines: Int = Int.MAX_VALUE,
    minLines: Int = 1,
    onTextLayout: ((TextLayoutResult) -> Unit)? = null,
    style: TextStyle = LocalTextStyle.current,
) {
    val localized = JaOverlay.tr(LocalContext.current, text)
    androidx.compose.material3.Text(
        text = localized,
        modifier = modifier,
        color = color,
        fontSize = fontSize,
        fontStyle = fontStyle,
        fontWeight = fontWeight,
        fontFamily = fontFamily,
        letterSpacing = letterSpacing,
        textDecoration = textDecoration,
        textAlign = textAlign,
        lineHeight = lineHeight,
        overflow = overflow,
        softWrap = softWrap,
        maxLines = maxLines,
        minLines = minLines,
        onTextLayout = onTextLayout,
        style = style,
    )
}

@Composable
fun Text(
    text: AnnotatedString,
    modifier: Modifier = Modifier,
    color: Color = Color.Unspecified,
    fontSize: TextUnit = TextUnit.Unspecified,
    fontStyle: FontStyle? = null,
    fontWeight: FontWeight? = null,
    fontFamily: FontFamily? = null,
    letterSpacing: TextUnit = TextUnit.Unspecified,
    textDecoration: TextDecoration? = null,
    textAlign: TextAlign? = null,
    lineHeight: TextUnit = TextUnit.Unspecified,
    overflow: TextOverflow = TextOverflow.Clip,
    softWrap: Boolean = true,
    maxLines: Int = Int.MAX_VALUE,
    minLines: Int = 1,
    inlineContent: Map<String, InlineTextContent> = mapOf(),
    onTextLayout: (TextLayoutResult) -> Unit = {},
    style: TextStyle = LocalTextStyle.current,
) {
    val localized = if (text.spanStyles.isEmpty() && text.paragraphStyles.isEmpty() && inlineContent.isEmpty()) {
        val tr = JaOverlay.tr(LocalContext.current, text.text)
        if (tr == text.text) text else AnnotatedString(tr)
    } else {
        text
    }
    androidx.compose.material3.Text(
        text = localized,
        modifier = modifier,
        color = color,
        fontSize = fontSize,
        fontStyle = fontStyle,
        fontWeight = fontWeight,
        fontFamily = fontFamily,
        letterSpacing = letterSpacing,
        textDecoration = textDecoration,
        textAlign = textAlign,
        lineHeight = lineHeight,
        overflow = overflow,
        softWrap = softWrap,
        maxLines = maxLines,
        minLines = minLines,
        inlineContent = inlineContent,
        onTextLayout = onTextLayout,
        style = style,
    )
}
