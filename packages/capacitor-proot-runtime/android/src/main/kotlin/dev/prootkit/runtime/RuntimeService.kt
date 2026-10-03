package dev.prootkit.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.system.Os
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Serviço em primeiro plano dono do runtime Linux: instala o rootfs a partir dos assets do APK
 * (1ª vez ou depois de uma atualização), sobe o servidor dentro do PRoot e o vigia. O Android ainda
 * pode matá-lo por pressão de memória; a notificação só diminui a chance.
 */
class RuntimeService : Service() {
    private var process: Process? = null
    private var worker: Thread? = null
    private lateinit var config: RuntimeConfig

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        config = RuntimeConfig.load(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopRuntime()
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        if (intent?.action == ACTION_RESTART) stopRuntime()
        if (worker?.isAlive != true && process?.isAlive != true) {
            worker = thread(name = "proot-runtime") { runRuntime() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopRuntime()
        super.onDestroy()
    }

    private fun runRuntime() {
        try {
            val layout = RuntimeLayout(this)
            installRootfsIfNeeded(layout)
            RuntimeStatus.set(RuntimeState.Starting)
            clearLeftovers(layout)
            val boot = UUID.randomUUID().toString()
            val token = Secrets(this).newApiToken()
            val proc = launchServer(layout, boot, token)
            process = proc
            if (waitUntilHealthy(proc, boot)) {
                RuntimeStatus.set(RuntimeState.Ready(Connection(config.baseUrl, token, boot, config.port)))
                val code = proc.waitFor()
                if (process === proc) RuntimeStatus.set(RuntimeState.Failed("O servidor parou (código $code).\n\n${layout.logTail()}"))
            } else if (process === proc) {
                proc.destroy()
                RuntimeStatus.set(RuntimeState.Failed("O servidor não respondeu.\n\n${layout.logTail()}"))
            }
        } catch (e: InterruptedException) {
            // stopRuntime(): parada ou reinício pedidos; o estado já foi atualizado lá.
        } catch (e: Exception) {
            Log.e(TAG, "runtime failed", e)
            RuntimeStatus.set(RuntimeState.Failed("${e.javaClass.simpleName}: ${e.message}"))
        }
    }

    private fun installRootfsIfNeeded(layout: RuntimeLayout) {
        val bundled = runCatching { assets.open(ROOTFS_VERSION_ASSET).bufferedReader().use { it.readText().trim() } }
            .getOrElse { error("O APK não tem $ROOTFS_VERSION_ASSET: rode scripts/build-rootfs.sh antes de compilar.") }
        if (layout.installedVersion.takeIf { it.exists() }?.readText()?.trim() == bundled && layout.rootfs.isDirectory) return

        RuntimeStatus.set(RuntimeState.Installing(0))
        val total = runCatching { assets.openFd(ROOTFS_ASSET).use { it.length } }.getOrDefault(-1L)
        val staging = File(layout.base, "rootfs.new").also { it.deleteRecursively() }
        RootfsExtractor { read ->
            if (total > 0) RuntimeStatus.set(RuntimeState.Installing((read * 100 / total).toInt().coerceIn(0, 99)))
        }.extract(assets.open(ROOTFS_ASSET).buffered(1 shl 16), staging)

        // Troca o rootfs; os dados do usuário moram fora dele (layout.home) e sobrevivem.
        val old = File(layout.base, "rootfs.old").also { it.deleteRecursively() }
        if (layout.rootfs.exists() && !layout.rootfs.renameTo(old)) error("Não consegui substituir o rootfs antigo")
        if (!staging.renameTo(layout.rootfs)) error("Não consegui ativar o rootfs novo")
        old.deleteRecursively()
        layout.installedVersion.writeText(bundled)
    }

    private fun launchServer(layout: RuntimeLayout, boot: String, token: String): Process {
        val nativeDir = applicationInfo.nativeLibraryDir
        layout.prepareDirectories()
        // O proot é linkado a "libtalloc.so.2"; o APK só consegue entregar libtalloc.so.
        File(layout.libs, "libtalloc.so.2").let {
            it.delete()
            Os.symlink("$nativeDir/libtalloc.so", it.path)
        }
        File(layout.rootfs, "etc/resolv.conf").let { it.delete(); it.writeText("nameserver 8.8.8.8\nnameserver 1.1.1.1\n") }
        // "localhost" tem que ser 127.0.0.1: servidores de dev escutam nele e o cliente conecta por IPv4.
        File(layout.rootfs, "etc/hosts").writeText("127.0.0.1 localhost\n::1 ip6-localhost ip6-loopback\n")

        val command = listOf(
            "$nativeDir/libproot.so",
            "--kill-on-exit", "-0", "--link2symlink",
            "-r", layout.rootfs.path,
            "-b", "/dev", "-b", "/proc", "-b", "/sys",
            "-b", "${layout.home.path}:/root",
            "-b", "${layout.tmp.path}:/tmp",
            "-w", "/root",
            "/bin/sh", config.entry,
        )
        val builder = ProcessBuilder(command).redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(layout.log))
        builder.environment().apply {
            clear()
            put("PROOT_LOADER", "$nativeDir/libproot-loader.so")
            put("PROOT_TMP_DIR", layout.tmp.path)
            put("LD_LIBRARY_PATH", "${layout.libs.path}:$nativeDir")
            put("HOME", "/root")
            put("PATH", "/usr/local/bin:/usr/bin:/bin")
            put("LANG", "C.UTF-8")
            putAll(config.env)
            put("APP_PORT", config.port.toString())
            put("APP_BOOT_ID", boot) // devolvido pelo health check: prova que é ESTE processo que responde
            put("APP_API_TOKEN", token)
            put("APP_SECRET_KEY", Secrets(this@RuntimeService).secretKey)
        }
        layout.log.appendText("\n==== ${java.util.Date()} iniciando servidor ====\n")
        return builder.start()
    }

    private fun waitUntilHealthy(proc: Process, boot: String): Boolean {
        val deadline = System.currentTimeMillis() + config.startupTimeoutMs
        while (System.currentTimeMillis() < deadline && proc.isAlive) {
            if (bootId() == boot) return true
            Thread.sleep(500)
        }
        return false
    }

    /** O boot id informado pelo servidor na porta, ou null se nada responde. */
    private fun bootId(): String? = runCatching {
        (URL(config.baseUrl + config.healthPath).openConnection() as HttpURLConnection).run {
            connectTimeout = 1000
            readTimeout = 2000
            try {
                if (responseCode != 200) null else JSONObject(inputStream.bufferedReader().readText()).optString("boot").ifEmpty { null }
            } finally { disconnect() }
        }
    }.getOrNull()

    /**
     * Um servidor antigo pode sobreviver ao seu PRoot (app morto pelo sistema, reinício): ele segura
     * a porta, o novo não consegue escutar e o antigo responderia ao health check. Antes de cada
     * partida, todo outro processo do usuário deste app (proot, python, servidores de dev) é morto —
     * o próprio app e os renderers da WebView (outros usuários) não são tocados — e a porta precisa
     * estar livre.
     */
    private fun clearLeftovers(layout: RuntimeLayout) {
        val me = android.os.Process.myPid()
        val uid = android.os.Process.myUid()
        val killed = File("/proc").listFiles { f -> f.name.all(Char::isDigit) }.orEmpty().mapNotNull { dir ->
            val pid = dir.name.toInt()
            if (pid == me) return@mapNotNull null
            val owner = runCatching { File(dir, "status").readLines().first { it.startsWith("Uid:") }.split(Regex("\\s+"))[1].toInt() }.getOrNull()
            if (owner != uid) return@mapNotNull null
            val cmd = runCatching { File(dir, "cmdline").readText().replace('\u0000', ' ').trim() }.getOrDefault("")
            if (cmd.startsWith(packageName)) return@mapNotNull null // processo(s) do próprio app
            android.os.Process.sendSignal(pid, android.os.Process.SIGNAL_KILL)
            "$pid ${cmd.take(60)}"
        }
        if (killed.isNotEmpty()) layout.log.appendText("\n==== processos antigos encerrados: ${killed.joinToString("; ")} ====\n")
        val deadline = System.currentTimeMillis() + 8_000
        while (portInUse() && System.currentTimeMillis() < deadline) Thread.sleep(250)
    }

    private fun portInUse(): Boolean =
        runCatching { java.net.Socket().use { it.connect(java.net.InetSocketAddress("127.0.0.1", config.port), 300) }; true }.getOrDefault(false)

    private fun stopRuntime() {
        val proc = process
        process = null
        proc?.destroy()
        worker?.interrupt()
        worker = null
        RuntimeStatus.set(RuntimeState.Idle)
    }

    private fun startInForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.proot_channel_name), NotificationManager.IMPORTANCE_LOW))
        val launch = packageManager.getLaunchIntentForPackage(packageName)
        val open = PendingIntent.getActivity(this, 0, launch, PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, RuntimeService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle(applicationInfo.loadLabel(packageManager))
            .setContentText(getString(R.string.proot_notification_text))
            .setContentIntent(open)
            .addAction(Notification.Action.Builder(null, getString(R.string.proot_stop), stop).build())
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    companion object {
        private const val TAG = "ProotRuntime"
        const val ACTION_RESTART = "dev.prootkit.runtime.RESTART"
        const val ACTION_STOP = "dev.prootkit.runtime.STOP"
        private const val CHANNEL = "proot_runtime"
        private const val NOTIFICATION_ID = 1
        private const val ROOTFS_ASSET = "rootfs.bin" // tar.gz; não ".gz": o empacotador descompactaria e renomearia
        private const val ROOTFS_VERSION_ASSET = "rootfs.version"

        fun start(context: Context, action: String? = null) {
            context.startForegroundService(Intent(context, RuntimeService::class.java).setAction(action))
        }

        /** Parar não precisa de notificação: é um start comum (o app está em primeiro plano). */
        fun stop(context: Context) {
            context.startService(Intent(context, RuntimeService::class.java).setAction(ACTION_STOP))
        }
    }
}
