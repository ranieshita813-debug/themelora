package com.example.rt;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Base64;
import android.os.IBinder;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.security.SecureRandom;
import java.util.Collections;

public class ShellService extends Service {

    public static final int PORT = 8080;
    private static final String CHANNEL = "remote_shell";
    private static final String PREFS = "server";
    private static final String KEY = "token";

    private static volatile boolean running = false;
    private static ShellServer server;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        NotificationChannel ch = new NotificationChannel(
                CHANNEL, "Remote shell", NotificationManager.IMPORTANCE_LOW);
        getSystemService(NotificationManager.class).createNotificationChannel(ch);

        Notification n = new Notification.Builder(this, CHANNEL)
                .setContentTitle("Remote shell running")
                .setContentText("Port " + PORT + ". Stop it from the app.")
                .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
                .setOngoing(true)
                .build();
        startForeground(1, n);

        // Always start a fresh server so a rotated token takes effect
        if (server != null) {
            server.stop();
            server = null;
        }
        try {
            server = new ShellServer(token(this), getFilesDir(), PORT);
            server.start();
            running = true;
        } catch (Exception e) {
            server = null;
            running = false;
            stopSelf();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (server != null) {
            server.stop();
            server = null;
        }
        running = false;
        super.onDestroy();
    }

    public static void start(Context c) {
        c.startForegroundService(new Intent(c, ShellService.class));
    }

    public static void stop(Context c) {
        c.stopService(new Intent(c, ShellService.class));
    }

    public static boolean isRunning() {
        return running;
    }

    public static String token(Context c) {
        SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String t = p.getString(KEY, null);
        if (t == null) {
            t = newToken();
            p.edit().putString(KEY, t).apply();
        }
        return t;
    }

    /** Stores a new token. If the server is running, press Start again to apply it. */
    public static void rotate(Context c) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(KEY, newToken()).apply();
    }

    public static String localIp() {
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!a.isLoopbackAddress() && a instanceof Inet4Address) {
                        return a.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) {
        }
        return "PHONE_IP";
    }

    private static String newToken() {
        byte[] b = new byte[32];
        new SecureRandom().nextBytes(b);
        return Base64.encodeToString(b, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }
}
