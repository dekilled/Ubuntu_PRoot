package dev.prootkit.runtime

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.OpenableColumns
import androidx.activity.result.ActivityResult
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin
import java.io.File
import kotlin.concurrent.thread

/**
 * Ponte Capacitor ⇄ runtime Linux. Só ciclo de vida, estado e credencial: o front fala HTTP direto
 * com o servidor usando a `connection` publicada quando o estado vira "ready".
 */
@CapacitorPlugin(name = "ProotRuntime")
class ProotRuntimePlugin : Plugin() {
    private var unobserve: (() -> Unit)? = null

    override fun load() {
        val config = RuntimeConfig.load(context)
        unobserve = RuntimeStatus.observe { notifyListeners("stateChange", RuntimeStatus.current.toJs()) }
        if (config.requestNotificationPermission && Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            activity.requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
        if (config.autoStart) RuntimeService.start(context)
    }

    override fun handleOnDestroy() {
        unobserve?.invoke()
        super.handleOnDestroy()
    }

    @PluginMethod
    fun start(call: PluginCall) {
        RuntimeService.start(context)
        call.resolve(RuntimeStatus.current.toJs())
    }

    @PluginMethod
    fun stop(call: PluginCall) {
        RuntimeService.stop(context)
        call.resolve()
    }

    @PluginMethod
    fun restart(call: PluginCall) {
        RuntimeService.start(context, RuntimeService.ACTION_RESTART)
        call.resolve(RuntimeStatus.current.toJs())
    }

    @PluginMethod
    fun getStatus(call: PluginCall) = call.resolve(RuntimeStatus.current.toJs())

    @PluginMethod
    fun getLogs(call: PluginCall) {
        val lines = (call.getInt("lines") ?: 150).coerceIn(1, 2000)
        call.resolve(JSObject().put("backend", RuntimeLayout(context).logTail(lines)))
    }

    /**
     * Seletor de arquivos do Android → cópia direta para a pasta de trabalho do Ubuntu
     * (/root/<filesDir>/<dir>), sem passar pela rede nem pela WebView. Progresso no evento
     * "importProgress". Cancelar o seletor resolve com `files: []`.
     */
    @PluginMethod
    fun importFiles(call: PluginCall) {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("*/*")
            .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        startActivityForResult(call, intent, "onFilesPicked")
    }

    @ActivityCallback
    private fun onFilesPicked(call: PluginCall?, result: ActivityResult) {
        call ?: return
        val data = result.data
        if (result.resultCode != Activity.RESULT_OK || data == null) return call.resolve(JSObject().put("files", JSArray()))
        val uris = data.clipData?.let { clip -> List(clip.itemCount) { clip.getItemAt(it).uri } } ?: listOfNotNull(data.data)

        val home = RuntimeLayout(context).home
        val root = File(home, RuntimeConfig.load(context).filesDir).also { it.mkdirs() }
        val dest = FileImport.resolveInside(root, call.getString("dir"))
        if (dest == null || !dest.isDirectory) return call.reject("Pasta de destino inválida: ${call.getString("dir")}")

        thread(name = "proot-import") {
            val saved = JSArray()
            try {
                uris.forEachIndexed { index, uri -> saved.put(copyOne(uri, dest, home, index, uris.size)) }
                call.resolve(JSObject().put("files", saved))
            } catch (e: Exception) {
                call.reject("Não consegui copiar o arquivo: ${e.message}", e)
            }
        }
    }

    private fun copyOne(uri: Uri, dest: File, home: File, index: Int, count: Int): JSObject {
        var name: String? = null
        var total = -1L
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                name = c.getString(0)
                if (!c.isNull(1)) total = c.getLong(1)
            }
        }
        val target = FileImport.freeTarget(dest, FileImport.safeName(name ?: uri.lastPathSegment) ?: "arquivo")
        val part = File(target.parentFile, target.name + ".part")
        try {
            val input = context.contentResolver.openInputStream(uri) ?: error("sem acesso a ${target.name}")
            input.use { inp ->
                part.outputStream().use { out ->
                    val buf = ByteArray(1 shl 16)
                    var loaded = 0L
                    var lastReport = 0L
                    while (true) {
                        val n = inp.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        loaded += n
                        if (loaded - lastReport >= PROGRESS_STEP) {
                            lastReport = loaded
                            progress(target.name, index, count, loaded, total)
                        }
                    }
                    progress(target.name, index, count, loaded, total)
                }
            }
            if (!part.renameTo(target)) error("não consegui gravar ${target.name}")
        } finally {
            part.delete()
        }
        return JSObject().put("name", target.name).put("size", target.length())
            .put("path", "/root/" + target.relativeTo(home).invariantSeparatorsPath)
    }

    private fun progress(name: String, index: Int, count: Int, loaded: Long, total: Long) = notifyListeners(
        "importProgress",
        JSObject().put("name", name).put("index", index).put("count", count).put("loaded", loaded).put("total", total),
    )

    private companion object {
        const val REQUEST_NOTIFICATIONS = 4270
        const val PROGRESS_STEP = 512L * 1024
    }
}

internal fun RuntimeState.toJs(): JSObject = JSObject().apply {
    put("state", name)
    when (val s = this@toJs) {
        is RuntimeState.Installing -> put("progress", s.percent)
        is RuntimeState.Failed -> put("message", s.message)
        is RuntimeState.Ready -> put(
            "connection",
            JSObject().put("baseUrl", s.connection.baseUrl).put("token", s.connection.token)
                .put("bootId", s.connection.bootId).put("port", s.connection.port),
        )
        else -> Unit
    }
}
