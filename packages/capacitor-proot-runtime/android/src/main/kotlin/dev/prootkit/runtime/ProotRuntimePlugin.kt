package dev.prootkit.runtime

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

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

    private companion object {
        const val REQUEST_NOTIFICATIONS = 4270
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
