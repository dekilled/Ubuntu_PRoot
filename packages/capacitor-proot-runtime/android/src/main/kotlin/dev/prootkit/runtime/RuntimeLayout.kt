package dev.prootkit.runtime

import android.content.Context
import java.io.File

/** Onde o runtime mora no armazenamento privado do app. */
class RuntimeLayout(context: Context) {
    val base: File = File(context.filesDir, "runtime")
    val rootfs = File(base, "rootfs")
    val installedVersion = File(base, "rootfs.installed")

    /** Montado como `/root` no PRoot: banco, arquivos e caches do app. Sobrevive à troca do rootfs. */
    val home = File(base, "home")
    val tmp = File(base, "tmp")
    val libs = File(base, "lib")
    val log = File(base, "backend.log")

    fun prepareDirectories() {
        listOf(base, home, tmp, libs).forEach { it.mkdirs() }
        if (log.length() > MAX_LOG_BYTES) log.writeText(log.readText().takeLast(MAX_LOG_BYTES / 2))
    }

    fun logTail(lines: Int = 40): String =
        if (log.exists()) log.readLines().takeLast(lines).joinToString("\n") else "(sem log)"

    private companion object {
        const val MAX_LOG_BYTES = 1 shl 20
    }
}
