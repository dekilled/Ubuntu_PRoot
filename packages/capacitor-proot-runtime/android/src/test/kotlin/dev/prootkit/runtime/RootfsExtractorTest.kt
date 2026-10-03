package dev.prootkit.runtime

import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream
import org.apache.commons.compress.archivers.tar.TarConstants
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.util.zip.GZIPOutputStream

class RootfsExtractorTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private class TarBuilder {
        private val bytes = ByteArrayOutputStream()
        private val tar = TarArchiveOutputStream(GZIPOutputStream(bytes)).apply { setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX) }

        fun dir(name: String, mode: Int = "755".toInt(8)) = apply { put(TarArchiveEntry("$name/").also { it.mode = mode }) }
        fun file(name: String, content: String, mode: Int = "644".toInt(8)) = apply {
            val data = content.toByteArray()
            tar.putArchiveEntry(TarArchiveEntry(name).also { it.size = data.size.toLong(); it.mode = mode })
            tar.write(data)
            tar.closeArchiveEntry()
        }
        fun symlink(name: String, target: String) = apply {
            put(TarArchiveEntry(name, TarConstants.LF_SYMLINK).also { it.linkName = target })
        }
        fun hardlink(name: String, target: String) = apply {
            put(TarArchiveEntry(name, TarConstants.LF_LINK).also { it.linkName = target })
        }
        private fun put(e: TarArchiveEntry) { tar.putArchiveEntry(e); tar.closeArchiveEntry() }
        fun build(): ByteArrayInputStream { tar.close(); return ByteArrayInputStream(bytes.toByteArray()) }
    }

    private fun mode(f: File) = Files.getPosixFilePermissions(f.toPath())

    @Test
    fun extractsFilesDirsSymlinksHardlinksAndModes() {
        val dest = tmp.newFolder("rootfs")
        val archive = TarBuilder()
            .dir("usr").dir("usr/bin")
            .file("usr/bin/python3", "#!elf", "755".toInt(8))
            .symlink("bin", "usr/bin")
            .symlink("etc/alternatives/python", "/usr/bin/python3")
            .hardlink("usr/bin/python3.12", "usr/bin/python3")
            .file("./opt/app/entry.sh", "echo hi", "700".toInt(8))
            .file("opt/" + "x".repeat(150) + "/long.txt", "long name")
            .build()

        var lastProgress = -1L
        RootfsExtractor { lastProgress = it }.extract(archive, dest)

        assertEquals("#!elf", File(dest, "usr/bin/python3").readText())
        assertTrue(File(dest, "usr/bin/python3").canExecute())
        assertTrue(Files.isSymbolicLink(File(dest, "bin").toPath()))
        assertEquals("usr/bin", Files.readSymbolicLink(File(dest, "bin").toPath()).toString())
        // Absolute symlinks are kept verbatim (meaningful only inside PRoot).
        assertEquals("/usr/bin/python3", Files.readSymbolicLink(File(dest, "etc/alternatives/python").toPath()).toString())
        assertEquals("#!elf", File(dest, "usr/bin/python3.12").readText())
        assertFalse(Files.isSymbolicLink(File(dest, "usr/bin/python3.12").toPath()))
        assertEquals("echo hi", File(dest, "opt/app/entry.sh").readText())
        assertEquals(3, mode(File(dest, "opt/app/entry.sh")).size) // rwx------
        assertEquals("long name", File(dest, "opt/" + "x".repeat(150) + "/long.txt").readText())
        assertTrue(lastProgress > 0)
    }

    @Test
    fun ignoresEntriesEscapingTheDestination() {
        val base = tmp.newFolder("base")
        val dest = File(base, "rootfs")
        val archive = TarBuilder()
            .file("../evil.txt", "nope")
            .file("/abs.txt", "absolute paths are made relative")
            .file("a/../../evil2.txt", "nope")
            .build()

        RootfsExtractor().extract(archive, dest)

        assertFalse(File(base, "evil.txt").exists())
        assertFalse(File(base, "evil2.txt").exists())
        assertEquals("absolute paths are made relative", File(dest, "abs.txt").readText())
    }

    @Test(expected = IOException::class)
    fun refusesToWriteThroughASymlink() {
        val outside = tmp.newFolder("outside")
        val dest = tmp.newFolder("rootfs2")
        val archive = TarBuilder()
            .symlink("escape", outside.absolutePath)
            .file("escape/pwned.txt", "nope")
            .build()
        try {
            RootfsExtractor().extract(archive, dest)
        } finally {
            assertFalse(File(outside, "pwned.txt").exists())
        }
    }

    @Test
    fun hardlinkToOutsideIsSkipped() {
        val base = tmp.newFolder("base2")
        File(base, "secret.txt").writeText("secret")
        val dest = File(base, "rootfs")
        RootfsExtractor().extract(TarBuilder().hardlink("copy.txt", "../secret.txt").build(), dest)
        assertFalse(File(dest, "copy.txt").exists())
    }

    @Test
    fun reExtractingOverwritesFilesAndSymlinks() {
        val dest = tmp.newFolder("rootfs3")
        RootfsExtractor().extract(TarBuilder().file("f", "v1").symlink("l", "f").build(), dest)
        RootfsExtractor().extract(TarBuilder().file("f", "v2").symlink("l", "g").build(), dest)
        assertEquals("v2", File(dest, "f").readText())
        assertEquals("g", Files.readSymbolicLink(File(dest, "l").toPath()).toString())
    }
}
