package dev.prootkit.runtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class RuntimeConfigTest {
    @Test
    fun readsPluginSectionOfCapacitorConfig() {
        val c = RuntimeConfig.parse(
            """{"appId":"x","plugins":{"ProotRuntime":{"port":9000,"entry":"/opt/x.sh","healthPath":"/h",
               "autoStart":false,"env":{"FOO":"bar","N":1}}}}""",
        )
        assertEquals(9000, c.port)
        assertEquals("/opt/x.sh", c.entry)
        assertEquals("/h", c.healthPath)
        assertFalse(c.autoStart)
        assertEquals(mapOf("FOO" to "bar", "N" to "1"), c.env)
        assertEquals("http://127.0.0.1:9000", c.baseUrl)
    }

    @Test
    fun fallsBackToDefaultsWhenSectionIsMissingOrJsonIsBroken() {
        assertEquals(RuntimeConfig(), RuntimeConfig.parse("""{"appId":"x"}"""))
        assertEquals(RuntimeConfig(), RuntimeConfig.parse("not json"))
    }
}
