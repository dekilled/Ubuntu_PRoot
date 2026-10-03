package dev.prootkit.runtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.file.Files

class FileImportTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun safeNameKeepsOnlyTheFileName() {
        assertEquals("evil.sh", FileImport.safeName("../../etc/evil.sh"))
        assertEquals("a.txt", FileImport.safeName("C:\\Users\\x\\a.txt"))
        assertEquals("foto 1.jpg", FileImport.safeName("  foto 1.jpg "))
        assertEquals("ab", FileImport.safeName("a\u0000b"))
        assertNull(FileImport.safeName(".."))
        assertNull(FileImport.safeName(""))
        assertNull(FileImport.safeName(null))
    }

    @Test
    fun resolveInsideNeverEscapesTheRoot() {
        val root = tmp.newFolder("files")
        File(root, "proj/src").mkdirs()
        assertEquals(root.canonicalFile, FileImport.resolveInside(root, ""))
        assertEquals(File(root, "proj/src").canonicalFile, FileImport.resolveInside(root, "/proj/src"))
        assertNull(FileImport.resolveInside(root, ".."))
        assertNull(FileImport.resolveInside(root, "proj/../../x"))
        val sibling = tmp.newFolder("files-irmao") // mesmo prefixo de nome, outra pasta
        assertNull(FileImport.resolveInside(root, "../${sibling.name}"))
        Files.createSymbolicLink(File(root, "atalho").toPath(), tmp.root.toPath())
        assertNull(FileImport.resolveInside(root, "atalho"))
    }

    @Test
    fun freeTargetNeverOverwrites() {
        val dir = tmp.newFolder("d")
        assertEquals("foto.jpg", FileImport.freeTarget(dir, "foto.jpg").name)
        File(dir, "foto.jpg").writeText("1")
        File(dir, "foto (1).jpg").writeText("2")
        assertEquals("foto (2).jpg", FileImport.freeTarget(dir, "foto.jpg").name)
        File(dir, "README").writeText("x")
        assertEquals("README (1)", FileImport.freeTarget(dir, "README").name)
        File(dir, ".bashrc").writeText("x")
        assertEquals(".bashrc (1)", FileImport.freeTarget(dir, ".bashrc").name)
    }
}
