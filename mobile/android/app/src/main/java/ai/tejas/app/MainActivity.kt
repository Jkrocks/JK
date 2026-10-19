package ai.tejas.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.http.SslError
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * Tejas AI for Android phones, tablets and TVs.
 *
 * Tejas's brain runs on the family's home computer. This app finds it on the
 * home Wi-Fi, pairs with it (the family checks a short code), and from then on
 * only trusts that computer's own "Tejas Home CA" certificate.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private val ui = Handler(Looper.getMainLooper())
    private val pool = Executors.newFixedThreadPool(32)
    private val prefs by lazy { getSharedPreferences("tejas", MODE_PRIVATE) }
    private val pendingCa = Collections.synchronizedMap(HashMap<String, String>())
    private var pendingMic: PermissionRequest? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        web = WebView(this)
        web.setBackgroundColor(0xFF050B0B.toInt())
        setContentView(web)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.settings.allowFileAccess = false
        web.addJavascriptInterface(Bridge(), "TejasApp")
        web.webViewClient = Client()
        web.webChromeClient = Chrome()
        val saved = prefs.getString("url", null)
        if (saved != null) web.loadUrl(saved) else showConnect(null)
    }

    private fun showConnect(message: String?) {
        val hash = if (message != null) "#" + Uri.encode(message) else ""
        web.loadUrl("file:///android_asset/connect.html$hash")
    }

    private fun js(fn: String, data: JSONObject) {
        ui.post { web.evaluateJavascript("window.$fn && window.$fn($data)", null) }
    }

    // ---- Certificates ---------------------------------------------------
    private fun trustedCas(): List<X509Certificate> {
        val cf = CertificateFactory.getInstance("X.509")
        return (prefs.getString("cas", "") ?: "").split("\n").filter { it.isNotBlank() }.mapNotNull {
            try {
                cf.generateCertificate(Base64.decode(it, Base64.NO_WRAP).inputStream()) as X509Certificate
            } catch (e: Exception) {
                null
            }
        }
    }

    private fun signedByTrustedCa(leaf: X509Certificate?): Boolean {
        if (leaf == null) return false
        return trustedCas().any { ca ->
            try {
                leaf.checkValidity()
                leaf.verify(ca.publicKey)
                true
            } catch (e: Exception) {
                false
            }
        }
    }

    private fun shortCode(cert: X509Certificate): String {
        val hex = MessageDigest.getInstance("SHA-256").digest(cert.encoded).joinToString("") { "%02X".format(it) }
        return hex.substring(0, 16).chunked(4).joinToString(" ")
    }

    /** Used only to find and pair with Tejas (reads /api/status and notes its certificate). */
    private class Capture : X509TrustManager {
        @Volatile var chain: Array<X509Certificate> = emptyArray()
        override fun checkClientTrusted(c: Array<X509Certificate>, a: String) {}
        override fun checkServerTrusted(c: Array<X509Certificate>, a: String) { chain = c }
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }

    private fun status(base: String, timeoutMs: Int): Pair<JSONObject, Array<X509Certificate>>? {
        val cap = Capture()
        val ctx = SSLContext.getInstance("TLS")
        ctx.init(null, arrayOf(cap), SecureRandom())
        var c: HttpsURLConnection? = null
        return try {
            c = URL("$base/api/status").openConnection() as HttpsURLConnection
            c.sslSocketFactory = ctx.socketFactory
            c.setHostnameVerifier { _, _ -> true }
            c.connectTimeout = timeoutMs
            c.readTimeout = timeoutMs * 4
            val body = c.inputStream.bufferedReader().use { it.readText() }
            val j = JSONObject(body)
            if (j.has("version")) Pair(j, cap.chain) else null
        } catch (e: Exception) {
            null
        } finally {
            c?.disconnect()
        }
    }

    private fun normalise(input: String): String {
        var s = input.trim().trimEnd('/')
        if (!s.startsWith("http")) s = "https://$s"
        s = s.replace("http://", "https://")
        val u = Uri.parse(s)
        return if (u.port == -1) "https://${u.host}:8443" else "https://${u.host}:${u.port}"
    }

    private fun lanPrefixes(): List<String> {
        val ips = try {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback }
                .flatMap { it.inetAddresses.toList() }
                .filterIsInstance<Inet4Address>()
                .mapNotNull { it.hostAddress }
        } catch (e: Exception) {
            emptyList()
        }
        val private = Regex("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.)")
        return ips.filter { private.containsMatchIn(it) }.map { it.substringBeforeLast('.') }.distinct()
    }

    // ---- Called from connect.html -------------------------------------------
    private inner class Bridge {
        @JavascriptInterface
        fun platform(): String = "android"

        @JavascriptInterface
        fun saved(): String = prefs.getString("url", "") ?: ""

        @JavascriptInterface
        fun scan() {
            pool.execute {
                val prefixes = lanPrefixes()
                if (prefixes.isEmpty()) {
                    js("onScanDone", JSONObject().put("error", "This device isn't on a home Wi-Fi network."))
                    return@execute
                }
                val targets = prefixes.flatMap { p -> (1..254).map { "$p.$it" } }
                val left = AtomicInteger(targets.size)
                for (ip in targets) {
                    pool.execute {
                        val base = "https://$ip:8443"
                        status(base, 800)?.let { (j, _) ->
                            js("onFound", JSONObject().put("url", base).put("name", j.optString("name", "Tejas")))
                        }
                        if (left.decrementAndGet() == 0) js("onScanDone", JSONObject())
                    }
                }
            }
        }

        @JavascriptInterface
        fun probe(input: String) {
            pool.execute {
                val base = try { normalise(input) } catch (e: Exception) { "" }
                val res = if (base.isEmpty()) null else status(base, 4000)
                if (res == null || res.second.isEmpty()) {
                    js("onProbe", JSONObject().put("ok", false).put("url", base)
                        .put("error", "Couldn't reach Tejas there. Check the address and that the home computer is on."))
                    return@execute
                }
                val chain = res.second
                val ca = chain.lastOrNull { it.subjectX500Principal == it.issuerX500Principal } ?: chain.last()
                pendingCa[base] = Base64.encodeToString(ca.encoded, Base64.NO_WRAP)
                js("onProbe", JSONObject().put("ok", true).put("url", base)
                    .put("name", res.first.optString("name", "Tejas")).put("code", shortCode(ca)))
            }
        }

        @JavascriptInterface
        fun trust(url: String) {
            ui.post {
                val ca = pendingCa[url] ?: return@post
                val cas = (prefs.getString("cas", "") ?: "").split("\n").filter { it.isNotBlank() }.toMutableSet()
                cas.add(ca)
                prefs.edit().putString("cas", cas.joinToString("\n")).putString("url", url).apply()
                web.loadUrl(url)
            }
        }

        @JavascriptInterface
        fun forget() {
            ui.post {
                prefs.edit().remove("url").apply()
                showConnect(null)
            }
        }
    }

    // ---- Web view ------------------------------------------------------------
    private inner class Client : WebViewClient() {
        override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
            if (signedByTrustedCa(error.certificate.x509Certificate)) {
                handler.proceed()
            } else {
                handler.cancel()
                showConnect("This computer isn't paired yet, or its security key changed. Pair again.")
            }
        }

        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val u = request.url
            val home = Uri.parse(prefs.getString("url", "") ?: "")
            if (u.scheme == "file" || (u.host == home.host && u.port == home.port)) return false
            startActivity(Intent(Intent.ACTION_VIEW, u))
            return true
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame && request.url.scheme == "https") {
                showConnect("Can't reach Tejas at ${request.url.host}. Is the home computer on and Tejas running?")
            }
        }
    }

    private inner class Chrome : WebChromeClient() {
        override fun onPermissionRequest(request: PermissionRequest) {
            ui.post {
                if (!request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
                    request.deny()
                } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else {
                    pendingMic = request
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 7)
                }
            }
        }
    }

    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        val r = pendingMic ?: return
        pendingMic = null
        if (results.isNotEmpty() && results[0] == PackageManager.PERMISSION_GRANTED) {
            r.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
        } else {
            r.deny()
        }
    }

    @Deprecated("Back on phones and TV remotes")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        pool.shutdownNow()
        web.destroy()
        super.onDestroy()
    }
}
