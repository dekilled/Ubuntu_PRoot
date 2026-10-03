package dev.prootkit.runtime

import android.os.Handler
import android.os.Looper
import java.util.concurrent.CopyOnWriteArraySet

/** Como o front fala com o servidor (entregue só quando ele está pronto). */
data class Connection(val baseUrl: String, val token: String, val bootId: String, val port: Int)

/** Estado do runtime, compartilhado entre [RuntimeService] (produtor) e o plugin (UI). */
sealed class RuntimeState(val name: String) {
    data object Idle : RuntimeState("idle")
    data class Installing(val percent: Int) : RuntimeState("installing")
    data object Starting : RuntimeState("starting")
    data class Ready(val connection: Connection) : RuntimeState("ready")
    data class Failed(val message: String) : RuntimeState("failed")
}

object RuntimeStatus {
    private val main = Handler(Looper.getMainLooper())
    private val listeners = CopyOnWriteArraySet<(RuntimeState) -> Unit>()

    @Volatile
    var current: RuntimeState = RuntimeState.Idle
        private set

    fun set(state: RuntimeState) {
        current = state
        main.post { listeners.forEach { it(state) } }
    }

    /** Registra [listener] (chamar da thread principal) e já reenvia o estado atual. */
    fun observe(listener: (RuntimeState) -> Unit): () -> Unit {
        listeners += listener
        listener(current)
        return { listeners -= listener }
    }
}
