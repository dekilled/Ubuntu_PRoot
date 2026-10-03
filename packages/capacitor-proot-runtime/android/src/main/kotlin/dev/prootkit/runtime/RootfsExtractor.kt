package dev.prootkit.runtime

import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import java.io.File
import java.io.FilterInputStream
import java.io.IOException
import java.io.InputStream
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Paths
import java.nio.file.attribute.PosixFilePermission
import java.util.zip.GZIPInputStream

/**
 * Extracts a gzip'd tar of a Linux root filesystem. Plain JVM code (no Android APIs) so it is
 * unit-tested on the build machine.
 *
 * - Entries escaping [dest] (absolute paths, "..") are rejected.
 * - Nothing is ever written through a symlink: the rootfs is full of absolute symlinks
 *   (/etc/alternatives/…) that only make sense inside PRoot; followed on the device they would
 *   point at the real Android filesystem.
 * - Hard links become copies (app storage does not allow hard links; PRoot's --link2symlink
 *   covers the ones created at runtime).
 * - Device nodes and FIFOs are skipped; PRoot binds the real /dev.
 */
class RootfsExtractor(private val onProgress: (bytesRead: Long) -> Unit = {}) {

    fun extract(gzipTar: InputStream, dest: File) {
        dest.mkdirs()
        val root = dest.canonicalFile
        val counter = CountingStream(gzipTar)
        TarArchiveInputStream(GZIPInputStream(counter, 1 shl 16)).use { tar ->
            var lastReport = 0L
            while (true) {
                val entry = tar.nextEntry ?: break
                val target = resolve(root, entry.name) ?: continue
                when {
                    entry.isDirectory -> {
                        ensureDirectory(root, target)
                        setMode(target, entry.mode or 0b111_000_000) // owner rwx: we must be able to write into it
                    }
                    entry.isSymbolicLink -> {
                        ensureDirectory(root, target.parentFile!!)
                        deleteIfPresent(target)
                        Files.createSymbolicLink(target.toPath(), Paths.get(entry.linkName))
                    }
                    entry.isLink -> {
                        val source = resolve(root, entry.linkName)
                        if (source != null && isInside(root, source) && source.isFile) {
                            ensureDirectory(root, target.parentFile!!)
                            deleteIfPresent(target)
                            source.copyTo(target)
                            setMode(target, entry.mode)
                        }
                    }
                    entry.isFile -> {
                        ensureDirectory(root, target.parentFile!!)
                        deleteIfPresent(target)
                        target.outputStream().use { tar.copyTo(it, 1 shl 16) }
                        setMode(target, entry.mode or 0b110_000_000) // owner rw
                    }
                    else -> Unit // character/block devices, FIFOs
                }
                if (counter.count - lastReport >= PROGRESS_STEP) {
                    lastReport = counter.count
                    onProgress(counter.count)
                }
            }
        }
        onProgress(counter.count)
    }

    /** Maps an archive path to a file under [root], or null when it would escape it. */
    private fun resolve(root: File, name: String): File? {
        val clean = name.trimStart('/').removePrefix("./")
        if (clean.isEmpty() || clean == ".") return null
        val parts = clean.split('/').filter { it.isNotEmpty() && it != "." }
        if (parts.any { it == ".." }) return null
        return File(root, parts.joinToString(File.separator))
    }

    /** Creates [dir] (and parents) refusing to go through symlinks or out of [root]. */
    private fun ensureDirectory(root: File, dir: File) {
        val chain = generateSequence(dir) { it.parentFile }.takeWhile { it != root }.toList().asReversed()
        for (d in chain) {
            val path = d.toPath()
            if (Files.isSymbolicLink(path)) throw IOException("Refusing to extract through symlink: $d")
            if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
                if (!d.mkdir() && !d.isDirectory) throw IOException("Cannot create $d")
            } else if (!d.isDirectory) {
                throw IOException("Not a directory: $d")
            }
        }
    }

    private fun isInside(root: File, f: File) = f.canonicalFile.toPath().startsWith(root.toPath())

    private fun deleteIfPresent(f: File) {
        val p = f.toPath()
        if (Files.exists(p, LinkOption.NOFOLLOW_LINKS) && !Files.isDirectory(p, LinkOption.NOFOLLOW_LINKS)) Files.delete(p)
    }

    private fun setMode(f: File, mode: Int) {
        val perms = mutableSetOf<PosixFilePermission>()
        PERMISSION_BITS.forEach { (bit, perm) -> if (mode and bit != 0) perms += perm }
        try {
            Files.setPosixFilePermissions(f.toPath(), perms)
        } catch (e: UnsupportedOperationException) {
            f.setReadable(true, false)
            f.setExecutable(mode and 0b001_001_001 != 0, false)
        }
    }

    private class CountingStream(input: InputStream) : FilterInputStream(input) {
        var count = 0L
            private set

        override fun read(): Int = super.read().also { if (it >= 0) count++ }
        override fun read(b: ByteArray, off: Int, len: Int): Int = super.read(b, off, len).also { if (it > 0) count += it }
        override fun skip(n: Long): Long = super.skip(n).also { count += it }
    }

    companion object {
        private const val PROGRESS_STEP = 4L shl 20
        private val PERMISSION_BITS = listOf(
            0b100_000_000 to PosixFilePermission.OWNER_READ,
            0b010_000_000 to PosixFilePermission.OWNER_WRITE,
            0b001_000_000 to PosixFilePermission.OWNER_EXECUTE,
            0b000_100_000 to PosixFilePermission.GROUP_READ,
            0b000_010_000 to PosixFilePermission.GROUP_WRITE,
            0b000_001_000 to PosixFilePermission.GROUP_EXECUTE,
            0b000_000_100 to PosixFilePermission.OTHERS_READ,
            0b000_000_010 to PosixFilePermission.OTHERS_WRITE,
            0b000_000_001 to PosixFilePermission.OTHERS_EXECUTE,
        )
    }
}
