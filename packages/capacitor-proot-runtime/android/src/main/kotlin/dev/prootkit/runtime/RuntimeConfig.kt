package dev.prootkit.runtime

import android.content.Context
import org.json.JSONObject

/**
 * Configuração do runtime, lida de `plugins.ProotRuntime` no `capacitor.config.json` (que o
 * `cap sync` copia para os assets). O serviço roda sem a ponte do Capacitor, por isso não usa
 * `PluginConfig`.
 */
data class RuntimeConfig(
    /** Porta do servidor em 127.0.0.1. */
    val port: Int = 8001,
    /** Script que roda dentro do rootfs e faz `exec` do servidor (recebe as variáveis `APP_*`). */
    val entry: String = "/opt/app/entry.sh",
    /** GET que devolve 200 + `{"boot": "<APP_BOOT_ID>"}` quando o servidor está de pé. */
    val healthPath: String = "/api/health",
    val startupTimeoutMs: Long = 180_000,
    /** Sobe o runtime assim que o plugin carrega. */
    val autoStart: Boolean = true,
    /** Pede a permissão de notificações (Android 13+) ao carregar. */
    val requestNotificationPermission: Boolean = true,
    /** Variáveis extras para o servidor. */
    val env: Map<String, String> = emptyMap(),
    /** Pasta (relativa a /root no Ubuntu) onde `importFiles` grava; casa com APP_FILES_DIR do entry.sh. */
    val filesDir: String = "files",
) {
    val baseUrl: String get() = "http://127.0.0.1:$port"

    companion object {
        fun parse(json: String): RuntimeConfig {
            val d = RuntimeConfig()
            val o = runCatching { JSONObject(json).optJSONObject("plugins")?.optJSONObject("ProotRuntime") }.getOrNull()
                ?: return d
            val extra = o.optJSONObject("env")
            return RuntimeConfig(
                port = o.optInt("port", d.port),
                entry = o.optString("entry", d.entry),
                healthPath = o.optString("healthPath", d.healthPath),
                startupTimeoutMs = o.optLong("startupTimeoutMs", d.startupTimeoutMs),
                autoStart = o.optBoolean("autoStart", d.autoStart),
                requestNotificationPermission = o.optBoolean("requestNotificationPermission", d.requestNotificationPermission),
                env = extra?.keys()?.asSequence()?.associateWith { extra.optString(it) } ?: emptyMap(),
                filesDir = o.optString("filesDir", d.filesDir),
            )
        }

        fun load(context: Context): RuntimeConfig =
            runCatching { context.assets.open("capacitor.config.json").bufferedReader().use { parse(it.readText()) } }
                .getOrDefault(RuntimeConfig())
    }
}
