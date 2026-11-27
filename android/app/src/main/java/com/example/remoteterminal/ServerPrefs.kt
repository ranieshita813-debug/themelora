package com.example.remoteterminal

import android.content.Context
import android.util.Base64
import java.security.SecureRandom

/**
 * Holds the remote access token. It is generated with SecureRandom on first use.
 * Plain SharedPreferences is used here, which is private to the app.
 * For stronger protection, move this to Android Keystore-backed storage.
 */
object ServerPrefs {
    private const val FILE = "server"
    private const val KEY = "token"

    fun token(context: Context): String {
        val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
        prefs.getString(KEY, null)?.let { return it }
        return newToken().also { prefs.edit().putString(KEY, it).apply() }
    }

    fun rotate(context: Context): String {
        val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
        return newToken().also { prefs.edit().putString(KEY, it).apply() }
    }

    private fun newToken(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }
}
