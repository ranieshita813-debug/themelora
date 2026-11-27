package com.example.rt;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.EOFException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

/**
 * Small HTTP + WebSocket server with no external libraries.
 *
 *   ws://host:PORT/shell           WebSocket shell (first text frame must be {"type":"auth","token":...})
 *   GET /files?token=...           list of images in the app folder
 *   GET /files/NAME?token=...      one image
 */
public class ShellServer {

    private static final String WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private static final Pattern NAME = Pattern.compile("^[A-Za-z0-9._-]+$");
    private static final List<String> IMAGE_EXT = Arrays.asList("jpg", "jpeg", "png", "gif", "webp");

    private final String token;
    private final File dir;
    private final int port;
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private volatile boolean running;
    private ServerSocket server;

    public ShellServer(String token, File dir, int port) {
        this.token = token;
        this.dir = dir;
        this.port = port;
    }

    public void start() throws IOException {
        server = new ServerSocket();
        server.setReuseAddress(true);
        server.bind(new InetSocketAddress("0.0.0.0", port));
        running = true;
        pool.execute(() -> {
            while (running) {
                try {
                    Socket s = server.accept();
                    pool.execute(() -> handle(s));
                } catch (IOException e) {
                    break;
                }
            }
        });
    }

    public void stop() {
        running = false;
        try {
            if (server != null) server.close();
        } catch (IOException ignored) {
        }
        pool.shutdownNow();
    }

    // ---------- HTTP and dispatch ----------

    private void handle(Socket s) {
        try {
            s.setSoTimeout(15_000);
            InputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();

            String requestLine = readLine(in);
            if (requestLine == null) return;

            Map<String, String> headers = new HashMap<>();
            String line;
            while ((line = readLine(in)) != null && !line.isEmpty()) {
                int colon = line.indexOf(':');
                if (colon > 0) {
                    headers.put(line.substring(0, colon).trim().toLowerCase(Locale.ROOT),
                            line.substring(colon + 1).trim());
                }
            }

            String[] parts = requestLine.split(" ");
            if (parts.length < 2) return;
            String method = parts[0];
            String target = parts[1];

            String path = target;
            String query = "";
            int q = target.indexOf('?');
            if (q >= 0) {
                path = target.substring(0, q);
                query = target.substring(q + 1);
            }

            if ("/shell".equals(path) && "websocket".equalsIgnoreCase(headers.get("upgrade"))) {
                handshake(headers, out);
                websocketSession(s, in, out);
                return;
            }

            if (!"GET".equals(method)) {
                send(out, 405, "text/plain", "method not allowed");
                return;
            }
            if (!authOk(queryParam(query, "token"))) {
                send(out, 401, "text/plain", "unauthorized");
                return;
            }
            if ("/files".equals(path)) {
                listFiles(out, queryParam(query, "token"));
            } else if (path.startsWith("/files/")) {
                serveFile(out, path.substring("/files/".length()));
            } else {
                send(out, 404, "text/plain", "not found");
            }
        } catch (Exception ignored) {
            // connection dropped or malformed request
        } finally {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }

    private boolean authOk(String given) {
        return given != null && MessageDigest.isEqual(
                given.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8));
    }

    private void listFiles(OutputStream out, String tok) throws IOException {
        StringBuilder html = new StringBuilder(
                "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>" +
                "<title>Files</title><body style='background:#111;color:#eee;font-family:sans-serif'>" +
                "<h3>Images</h3><ul>");
        File[] files = dir.listFiles();
        if (files != null) {
            Arrays.sort(files);
            for (File f : files) {
                if (isImage(f)) {
                    html.append("<li><a style='color:#8cf' href='/files/").append(f.getName())
                            .append("?token=").append(tok).append("'>")
                            .append(f.getName()).append("</a></li>");
                }
            }
        }
        html.append("</ul></body>");
        send(out, 200, "text/html; charset=utf-8", html.toString());
    }

    private void serveFile(OutputStream out, String name) throws IOException {
        File f = new File(dir, name);
        boolean inside = f.getCanonicalFile().getParentFile().equals(dir.getCanonicalFile());
        if (!inside || !isImage(f)) {
            send(out, 404, "text/plain", "not found");
            return;
        }
        byte[] data = Files.readAllBytes(f.toPath());
        String head = "HTTP/1.1 200 OK\r\nContent-Type: " + mime(f.getName()) +
                "\r\nContent-Length: " + data.length + "\r\nConnection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.US_ASCII));
        out.write(data);
        out.flush();
    }

    private boolean isImage(File f) {
        return f.isFile() && NAME.matcher(f.getName()).matches()
                && IMAGE_EXT.contains(ext(f.getName()));
    }

    private static String ext(String name) {
        int d = name.lastIndexOf('.');
        return d < 0 ? "" : name.substring(d + 1).toLowerCase(Locale.ROOT);
    }

    private static String mime(String name) {
        switch (ext(name)) {
            case "jpg":
            case "jpeg": return "image/jpeg";
            case "png": return "image/png";
            case "gif": return "image/gif";
            case "webp": return "image/webp";
            default: return "application/octet-stream";
        }
    }

    private static void send(OutputStream out, int code, String type, String body) throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        String reason;
        switch (code) {
            case 200: reason = "OK"; break;
            case 401: reason = "Unauthorized"; break;
            case 404: reason = "Not Found"; break;
            case 405: reason = "Method Not Allowed"; break;
            default: reason = "Error";
        }
        String head = "HTTP/1.1 " + code + " " + reason + "\r\nContent-Type: " + type +
                "\r\nContent-Length: " + b.length + "\r\nConnection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.US_ASCII));
        out.write(b);
        out.flush();
    }

    private static String readLine(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') break;
            if (c != '\r') sb.append((char) c);
            if (sb.length() > 8192) throw new IOException("line too long");
        }
        if (c == -1 && sb.length() == 0) return null;
        return sb.toString();
    }

    private static String queryParam(String query, String key) {
        for (String kv : query.split("&")) {
            int eq = kv.indexOf('=');
            if (eq > 0 && kv.substring(0, eq).equals(key)) {
                return kv.substring(eq + 1);
            }
        }
        return null;
    }

    // ---------- WebSocket ----------

    private void handshake(Map<String, String> headers, OutputStream out) throws IOException {
        String key = headers.get("sec-websocket-key");
        if (key == null) throw new IOException("missing Sec-WebSocket-Key");
        try {
            byte[] digest = MessageDigest.getInstance("SHA-1")
                    .digest((key + WS_GUID).getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String resp = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n" +
                    "Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n";
            out.write(resp.getBytes(StandardCharsets.US_ASCII));
            out.flush();
        } catch (Exception e) {
            throw new IOException(e);
        }
    }

    private void websocketSession(Socket s, InputStream in, OutputStream out) throws IOException {
        s.setSoTimeout(5_000);
        Frame first = readFrame(in);
        String given = (first != null && first.opcode == 1) ? tokenFrom(first.text()) : null;
        if (!authOk(given)) {
            writeFrame(out, 8, closePayload(1008));
            return;
        }
        s.setSoTimeout(0);

        ProcessBuilder pb = new ProcessBuilder("/system/bin/sh", "-i")
                .directory(dir)
                .redirectErrorStream(true);
        pb.environment().put("HOME", dir.getAbsolutePath());
        pb.environment().put("TERM", "dumb");
        pb.environment().put("PATH", "/system/bin:/system/xbin");
        Process p = pb.start();

        // Shell output -> WebSocket binary frames
        Thread pump = new Thread(() -> {
            try (InputStream pin = p.getInputStream()) {
                byte[] buf = new byte[4096];
                int n;
                while ((n = pin.read(buf)) != -1) {
                    synchronized (out) {
                        writeFrame(out, 2, Arrays.copyOf(buf, n));
                    }
                }
            } catch (IOException ignored) {
            } finally {
                try {
                    s.close();
                } catch (IOException ignored) {
                }
            }
        });
        pump.start();

        try {
            while (true) {
                Frame f = readFrame(in);
                if (f == null || f.opcode == 8) break;
                if (f.opcode == 9) {
                    synchronized (out) {
                        writeFrame(out, 10, f.payload);
                    }
                } else if (f.opcode == 2) {
                    // Keystrokes -> shell stdin
                    OutputStream stdin = p.getOutputStream();
                    stdin.write(f.payload);
                    stdin.flush();
                }
                // Text frames after auth (for example resize) are accepted but ignored: no PTY here.
            }
        } finally {
            p.destroy();
            s.close();
        }
    }

    private static String tokenFrom(String text) {
        try {
            JSONObject o = new JSONObject(text);
            return "auth".equals(o.optString("type")) ? o.optString("token", null) : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static byte[] closePayload(int code) {
        return new byte[]{(byte) (code >> 8), (byte) code};
    }

    static final class Frame {
        int opcode;
        byte[] payload;

        String text() {
            return new String(payload, StandardCharsets.UTF_8);
        }
    }

    private static Frame readFrame(InputStream in) throws IOException {
        int b0 = in.read();
        int b1 = in.read();
        if (b0 < 0 || b1 < 0) return null;

        int opcode = b0 & 0x0F;
        boolean masked = (b1 & 0x80) != 0;
        long len = b1 & 0x7F;
        if (len == 126) len = readN(in, 2);
        else if (len == 127) len = readN(in, 8);
        if (len > 1 << 20) throw new IOException("frame too large");

        byte[] mask = new byte[4];
        if (masked) readFully(in, mask);

        byte[] payload = new byte[(int) len];
        readFully(in, payload);
        if (masked) {
            for (int i = 0; i < payload.length; i++) {
                payload[i] ^= mask[i % 4];
            }
        }

        Frame f = new Frame();
        f.opcode = opcode;
        f.payload = payload;
        return f;
    }

    private static void writeFrame(OutputStream out, int opcode, byte[] payload) throws IOException {
        out.write(0x80 | opcode);
        int len = payload.length;
        if (len < 126) {
            out.write(len);
        } else if (len < 65536) {
            out.write(126);
            out.write(len >> 8);
            out.write(len & 0xFF);
        } else {
            out.write(127);
            for (int i = 7; i >= 0; i--) {
                out.write((int) (((long) len >>> (i * 8)) & 0xFF));
            }
        }
        out.write(payload);
        out.flush();
    }

    private static long readN(InputStream in, int n) throws IOException {
        long v = 0;
        for (int i = 0; i < n; i++) {
            int b = in.read();
            if (b < 0) throw new EOFException();
            v = (v << 8) | b;
        }
        return v;
    }

    private static void readFully(InputStream in, byte[] b) throws IOException {
        int off = 0;
        while (off < b.length) {
            int r = in.read(b, off, b.length - off);
            if (r < 0) throw new EOFException();
            off += r;
        }
    }
}
