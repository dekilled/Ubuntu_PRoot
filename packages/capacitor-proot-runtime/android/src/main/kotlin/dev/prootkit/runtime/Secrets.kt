package dev.prootkit.runtime

import android.content.Context
import java.security.SecureRandom

/**
 * Segredos do servidor, guardados nas preferências privadas do app e entregues só por variáveis
 * de ambiente.
 *
 * - [secretKey]: estável por instalação (`APP_SECRET_KEY`). Serve para cifrar dados em repouso /
 *   assinar coisas; **não pode mudar**, ou o que foi cifrado com ela deixa de abrir.
 * - [newApiToken]: novo a cada partida (`APP_API_TOKEN`); só quem fala com a ponte do Capacitor
 *   (o front do app) o recebe. Outros apps do celular alcançam 127.0.0.1 mas não têm o token.
 */
class Secrets(context: Context) {
    private val prefs = context.getSharedPreferences("proot_runtime_secrets", Context.MODE_PRIVATE)

    val secretKey: String
        @Synchronized get() = prefs.getString("secret_key", null)
            ?: hex(32).also { prefs.edit().putString("secret_key", it).commit() }

    fun newApiToken(): String = hex(24)

    private fun hex(bytes: Int): String =
        ByteArray(bytes).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
}
