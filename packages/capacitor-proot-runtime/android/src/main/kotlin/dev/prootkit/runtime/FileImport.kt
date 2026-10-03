package dev.prootkit.runtime

import java.io.File

/**
 * Regras para gravar arquivos escolhidos pelo usuário dentro da pasta de trabalho do Ubuntu.
 * JVM puro (sem APIs Android), testado em FileImportTest. Mesmas regras do servidor
 * (backend/app/routes/files.py): nome sem diretórios, nunca sobrescreve, nunca sai da pasta.
 */
object FileImport {
    /** Só o nome final, sem barras nem caracteres de controle; null se não sobrar nome válido. */
    fun safeName(raw: String?): String? {
        val base = (raw ?: "").replace('\\', '/').substringAfterLast('/')
        val clean = base.filter { !it.isISOControl() }.trim().take(200)
        return clean.takeUnless { it.isEmpty() || it == "." || it == ".." }
    }

    /** `dir` relativo a [root], ou null se escapar dela (por `..` ou symlink). */
    fun resolveInside(root: File, dir: String?): File? {
        val base = root.canonicalFile
        val target = File(base, (dir ?: "").trim().trimStart('/')).canonicalFile
        return target.takeIf { it == base || it.path.startsWith(base.path + File.separator) }
    }

    /** `foto.jpg` → `foto (1).jpg`, `foto (2).jpg`… enquanto já existir. */
    fun freeTarget(dir: File, name: String): File {
        var target = File(dir, name)
        val dot = name.lastIndexOf('.').takeIf { it > 0 } ?: name.length
        val stem = name.substring(0, dot)
        val ext = name.substring(dot)
        var n = 1
        while (target.exists()) target = File(dir, "$stem (${n++})$ext")
        return target
    }
}
