package com.example.rt;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {

    private TextView status;
    private TextView info;
    private boolean showToken = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(40, 80, 40, 40);
        root.setBackgroundColor(0xFF111111);

        status = new TextView(this);
        status.setTextSize(20);
        status.setTextColor(0xFFEEEEEE);

        info = new TextView(this);
        info.setTextSize(14);
        info.setTextColor(0xFFBBBBBB);
        info.setTextIsSelectable(true);

        root.addView(status);
        root.addView(info);

        LinearLayout row1 = new LinearLayout(this);
        row1.setOrientation(LinearLayout.HORIZONTAL);
        row1.addView(button("Start", v -> { ShellService.start(this); refreshLater(); }));
        row1.addView(button("Stop", v -> { ShellService.stop(this); refreshLater(); }));
        root.addView(row1);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        row2.addView(button("Show/Hide token", v -> { showToken = !showToken; refresh(); }));
        row2.addView(button("New token", v -> { ShellService.rotate(this); refresh(); }));
        root.addView(row2);

        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private Button button(String label, View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(label);
        b.setOnClickListener(listener);
        return b;
    }

    private void refreshLater() {
        // Give the service a moment to start or stop before reading its state
        getWindow().getDecorView().postDelayed(this::refresh, 500);
    }

    private void refresh() {
        status.setText(ShellService.isRunning()
                ? "Running on port " + ShellService.PORT
                : "Stopped");

        String ip = ShellService.localIp();
        String token = showToken ? ShellService.token(this) : "(hidden)";

        info.setText(
                "WebSocket: ws://" + ip + ":" + ShellService.PORT + "/shell\n\n" +
                "Browser file list:\nhttp://" + ip + ":" + ShellService.PORT +
                "/files?token=" + token + "\n\n" +
                "Token: " + token + "\n\n" +
                "After New token, press Stop and Start to apply it."
        );
    }
}
